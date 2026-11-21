"""Acknowledge verified payments, independently of AI and auto-shipping."""
import os
import asyncio
import re
import time
from sqlalchemy import select, text, func
from loguru import logger
from common.db.session import async_session_maker
from common.models.xy_order import XYOrder
from common.services.order_service import OrderStatusChecker
from app.services.xianyu.rate_service import check_item_belongs_to_account

REPLY = 'ok 收到'
PAID_MESSAGES = {'我已付款等待你发货', '我已付款等待你尽快发货', '已付款待发货', '买家已付款', '付款完成', '我已付款请添加自提信息'}

def is_paid_notice_text(value):
    return re.sub(r'[\s\[\]【】，,。！!]', '', str(value or '')).replace('您', '你') in PAID_MESSAGES

async def acknowledge_payment(owner, parsed, websocket):
    try:
        message = str(parsed.get('send_message') or '').strip().strip('[]').strip()
        if parsed.get('is_plain_text', True) or not is_paid_notice_text(message):
            return False
        raw = parsed.get('raw_message') or {}
        inner = raw.get('1')
        stamp = (inner.get('5') if isinstance(inner, dict) else raw.get('5'))
        enabled_at = float(os.environ.get('PAID_ACK_ENABLED_AT', '0'))
        if not enabled_at or not stamp or not enabled_at <= float(stamp)/1000 <= time.time()+60:
            return True
        order_id = owner._extract_order_id(raw)
        buyer = str(parsed.get('send_user_id') or '')
        chat = str(parsed.get('chat_id') or '').split('@')[0]
        item = str(parsed.get('item_id') or '')
        if not all((buyer, chat, item)) or buyer == str(owner.myid):
            return True
        if not order_id:
            # Status-update cards can omit the order URL; never guess between two orders.
            async with async_session_maker() as session:
                result = await session.execute(select(XYOrder).where(
                    XYOrder.account_id == owner.cookie_id,
                    XYOrder.buyer_id == buyer,
                    func.substring_index(XYOrder.chat_id, '@', 1) == chat,
                    XYOrder.item_id == item,
                    XYOrder.status.in_({'pending_payment', 'pending_ship', 'pending', 'paid', '待发货'}),
                    func.json_extract(XYOrder.metadata_json, '$.payment_ack').is_(None),
                ).limit(2))
                candidates = result.scalars().all()
            if len(candidates) != 1:
                return True
            order_id = candidates[0].order_no
        if not await check_item_belongs_to_account(owner.cookie_id, item):
            return True
        from app.services.xianyu.auto_reply_service import AutoReplyService
        delay = await AutoReplyService(owner.cookie_id, owner)._load_reply_delay()
        if delay > 0:
            await asyncio.sleep(delay)
        # Check payment after waiting so a refund during the delay cannot use stale verification.
        check = await OrderStatusChecker(owner.cookies_str, owner.cookie_id).check_can_ship(order_id)
        if check.get('success') is not True or check.get('can_ship') is not True:
            return True
        async with async_session_maker() as session:
            result = await session.execute(select(XYOrder).where(
                XYOrder.account_id == owner.cookie_id, XYOrder.order_no == order_id
            ).with_for_update())
            order = result.scalar_one_or_none()
            if not order or order.status not in {'pending_payment', 'pending_ship', 'pending', 'paid', '待发货'} or str(order.buyer_id) != buyer or str(order.chat_id or '').split('@')[0] != chat or str(order.item_id) != item:
                return True
            metadata = dict(order.metadata_json or {})
            if metadata.get('payment_ack'):
                return True
            if order.status == 'pending_payment':
                order.status = 'pending_ship'  # Fresh platform check above confirmed payment.
            metadata['payment_ack'] = {'state': 'reserved', 'text': REPLY}
            order.metadata_json = metadata
            row_id = order.id
            await session.commit()
        # Reserve durably before sending: an ambiguous send must not spam on replay/restart.
        sent = await owner.send_msg(websocket, chat, buyer, REPLY)
        state = 'submitted' if sent.get('success') is True else 'failed'
        async with async_session_maker() as session:
            await session.execute(text("UPDATE xy_orders SET metadata=JSON_SET(metadata, '$.payment_ack.state', :state) WHERE id=:id"), {'state': state, 'id': row_id})
            await session.commit()
        logger.info('Payment acknowledgement {} for order {}', state, order_id)
    except Exception as exc:
        # An uncertain socket outcome remains reserved for manual review, never blind resend.
        logger.warning('Payment acknowledgement stopped: {}', type(exc).__name__)
    return True
