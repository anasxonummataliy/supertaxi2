import os
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from telethon import TelegramClient, errors
from telethon.tl import types as tl_types
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import Chat, Channel
from telethon.tl.functions.channels import JoinChannelRequest

logger = logging.getLogger(__name__)

_clients: dict[str, TelegramClient] = {}
_pending_clients: dict[str, TelegramClient] = {}
_pending_hashes: dict[str, str] = {}
_pending_qr_clients: dict[int, TelegramClient] = {}
_pending_qr_logins: dict[int, object] = {}


def _get_api_credentials() -> tuple[int, str]:
    env_file = os.getenv("ENV_FILE")
    if env_file and os.path.exists(env_file):
        load_dotenv(dotenv_path=env_file)
    else:
        load_dotenv()

    api_id_raw = os.getenv("API_ID", "").strip()
    api_hash = os.getenv("API_HASH", "").strip()

    if not api_id_raw or not api_hash:
        raise RuntimeError(
            "API_ID yoki API_HASH topilmadi. .env faylda ikkala qiymat ham to'ldirilganini tekshiring."
        )

    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise RuntimeError("API_ID butun son bo'lishi kerak.") from exc

    return api_id, api_hash


def _build_client(session_string: str | None = None) -> TelegramClient:
    api_id, api_hash = _get_api_credentials()
    return TelegramClient(StringSession(session_string or ""), api_id, api_hash)


def _describe_sent_code(sent_code) -> dict[str, str | int | bool | None]:
    code_type = sent_code.type
    delivery_type = type(code_type).__name__
    info: dict[str, str | int | bool | None] = {
        "delivery_type": delivery_type,
        "delivery_hint": "📨 Kod yuborildi. Telegram ilovasi va SMS xabarlarni tekshiring.",
        "code_length": getattr(code_type, "length", None),
        "timeout_seconds": sent_code.timeout,
        "next_type": type(sent_code.next_type).__name__ if sent_code.next_type else None,
    }

    if isinstance(code_type, tl_types.auth.SentCodeTypeApp):
        info["delivery_hint"] = (
            "📲 Kod Telegram ilovasining ichiga yuborildi. SMS kutmang. "
            "Bu raqam kirilgan barcha Telegram qurilmalarini tekshiring: "
            "telefon, Telegram Desktop va Telegram xizmat xabarlari chatini."
        )
    elif isinstance(code_type, tl_types.auth.SentCodeTypeSms):
        info["delivery_hint"] = "📩 Kod SMS orqali yuborildi."
    elif isinstance(code_type, tl_types.auth.SentCodeTypeFirebaseSms):
        info["delivery_hint"] = (
            "📩 Kod SMS tasdiqlash oqimi orqali yuborildi. SMS va Telegram ilovasini tekshiring."
        )
    elif isinstance(code_type, tl_types.auth.SentCodeTypeCall):
        info["delivery_hint"] = "📞 Kod telefon qo'ng'irog'i orqali kelishi mumkin."
    elif isinstance(code_type, tl_types.auth.SentCodeTypeFlashCall):
        info["delivery_hint"] = (
            "📞 Telegram flash call ishlatmoqda. Kiruvchi qo'ng'iroq raqamidagi andoza kod bo'lishi mumkin."
        )
        info["code_length"] = None
    elif isinstance(code_type, tl_types.auth.SentCodeTypeMissedCall):
        info["delivery_hint"] = (
            "📞 Telegram missed call ishlatmoqda. Qisqa qo'ng'iroqdagi raqamlar kod sifatida ishlatiladi."
        )
        info["code_length"] = code_type.length
    elif isinstance(code_type, tl_types.auth.SentCodeTypeEmailCode):
        info["delivery_hint"] = (
            f"📧 Kod emailga yuborildi: {code_type.email_pattern}. "
            "Email pochtangizni tekshiring."
        )
    elif isinstance(code_type, tl_types.auth.SentCodeTypeFragmentSms):
        info["delivery_hint"] = (
            "📩 Telegram Fragment SMS usulidan foydalanyapti. Rasmiy Telegram ilovasidagi ko'rsatmaga amal qiling."
        )
    elif isinstance(code_type, tl_types.auth.SentCodeTypeSetUpEmailRequired):
        info["delivery_hint"] = (
            "📧 Bu akkaunt uchun Telegram email tasdiqlashni talab qilyapti. "
            "Avval rasmiy Telegram ilovasida login jarayonini yakunlab ko'ring."
        )

    return info


def _seconds_until(dt: datetime) -> int:
    return max(0, int((dt - datetime.now(timezone.utc)).total_seconds()))


def _format_begin_auth_error(exc: Exception) -> str:
    if isinstance(exc, errors.ApiIdInvalidError):
        return "API_ID yoki API_HASH noto'g'ri sozlangan."
    if isinstance(exc, errors.ApiIdPublishedFloodError):
        return "Ushbu API ma'lumotlari Telegram tomonidan vaqtincha bloklangan."
    if isinstance(exc, errors.PhoneNumberInvalidError):
        return "Telefon raqami noto'g'ri. Misol: +998901234567"
    if isinstance(exc, errors.PhoneNumberFloodError):
        return "Bu raqam uchun kod juda ko'p so'ralgan. Birozdan keyin qayta urinib ko'ring."
    if isinstance(exc, errors.PhoneNumberBannedError):
        return "Bu telefon raqami Telegram tomonidan bloklangan."
    if isinstance(exc, errors.PhonePasswordFloodError):
        return "Login urinishlari juda ko'p bo'ldi. Biroz kutib qayta urinib ko'ring."
    if isinstance(exc, errors.PhonePasswordProtectedError):
        return "Bu akkauntda qo'shimcha parol himoyasi yoqilgan. Koddan keyin 2FA paroli ham so'ralishi mumkin."
    return str(exc)


async def get_or_create_client(session_string: str, phone: str) -> TelegramClient:
    if phone in _clients:
        client = _clients[phone]
        if not client.is_connected():
            await client.connect()
        return client
    client = _build_client(session_string)
    await client.connect()
    _clients[phone] = client
    return client


async def begin_auth(phone: str) -> dict[str, str | int | bool | None]:
    client = _pending_clients.get(phone)
    is_resend = client is not None
    if not client:
        client = _build_client()

    try:
        if not client.is_connected():
            await client.connect()
        result = await client.send_code_request(phone)
    except Exception as exc:
        if not is_resend:
            try:
                await client.disconnect()
            except Exception:
                pass
            _pending_clients.pop(phone, None)
            _pending_hashes.pop(phone, None)
        raise RuntimeError(_format_begin_auth_error(exc)) from exc

    auth_info = _describe_sent_code(result)
    auth_info["is_resend"] = is_resend
    logger.info(
        "Auth code requested for %s: resend=%s delivery=%s next_type=%s timeout=%s",
        phone,
        is_resend,
        auth_info["delivery_type"],
        auth_info["next_type"],
        auth_info["timeout_seconds"],
    )
    _pending_clients[phone] = client
    if result.phone_code_hash:
        _pending_hashes[phone] = result.phone_code_hash
    return auth_info


async def begin_qr_auth(owner_id: int) -> dict[str, str | int]:
    await cancel_qr_auth(owner_id)

    client = _build_client()
    try:
        await client.connect()
        qr_login = await client.qr_login()
    except Exception:
        await client.disconnect()
        raise

    _pending_qr_clients[owner_id] = client
    _pending_qr_logins[owner_id] = qr_login

    expires_in = _seconds_until(qr_login.expires)
    logger.info("QR auth created for owner=%s expires_in=%ss", owner_id, expires_in)
    return {"url": qr_login.url, "expires_in": expires_in}


async def wait_for_qr_auth(owner_id: int) -> tuple:
    client = _pending_qr_clients.get(owner_id)
    qr_login = _pending_qr_logins.get(owner_id)
    if not client or not qr_login:
        raise RuntimeError("QR login topilmadi yoki muddati tugagan")

    try:
        await qr_login.wait()
        me = await client.get_me()
        session_string = client.session.save()
        await client.disconnect()
        _pending_qr_clients.pop(owner_id, None)
        _pending_qr_logins.pop(owner_id, None)
        return session_string, me, False
    except SessionPasswordNeededError:
        _pending_qr_logins.pop(owner_id, None)
        return None, None, True
    except Exception:
        await cancel_qr_auth(owner_id)
        raise


async def complete_qr_auth_2fa(owner_id: int, password: str) -> tuple:
    client = _pending_qr_clients.get(owner_id)
    if not client:
        raise RuntimeError("QR uchun pending client topilmadi")

    await client.sign_in(password=password)
    me = await client.get_me()
    session_string = client.session.save()
    await client.disconnect()
    _pending_qr_clients.pop(owner_id, None)
    _pending_qr_logins.pop(owner_id, None)
    return session_string, me


async def cancel_qr_auth(owner_id: int):
    client = _pending_qr_clients.pop(owner_id, None)
    _pending_qr_logins.pop(owner_id, None)
    if client:
        try:
            await client.disconnect()
        except Exception:
            pass


async def complete_auth(phone: str, code: str) -> tuple:
    client = _pending_clients.get(phone)
    if not client:
        raise RuntimeError("Pending client topilmadi")
    phone_code_hash = _pending_hashes.get(phone)
    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        me = await client.get_me()
        session_string = client.session.save()
        _clients[phone] = client
        _pending_clients.pop(phone, None)
        _pending_hashes.pop(phone, None)
        return session_string, me, False
    except SessionPasswordNeededError:
        return None, None, True


async def complete_auth_2fa(phone: str, password: str) -> tuple:
    client = _pending_clients.get(phone)
    if not client:
        raise RuntimeError("Pending client topilmadi")
    await client.sign_in(password=password)
    me = await client.get_me()
    session_string = client.session.save()
    _clients[phone] = client
    _pending_clients.pop(phone, None)
    _pending_hashes.pop(phone, None)
    return session_string, me


async def disconnect_client(phone: str):
    client = _clients.pop(phone, None)
    if client:
        try:
            await client.disconnect()
        except Exception:
            pass


async def disconnect_and_remove(phone: str):
    for store in (_clients, _pending_clients):
        if phone in store:
            try:
                await store[phone].disconnect()
            except Exception:
                pass
            del store[phone]
    _pending_hashes.pop(phone, None)


async def fetch_groups(session_string: str, phone: str) -> list:
    client = await get_or_create_client(session_string, phone)
    dialogs = await client.get_dialogs()
    groups = []
    for dialog in dialogs:
        entity = dialog.entity
        if isinstance(entity, Chat) and not entity.deactivated:
            groups.append(
                {"group_id": entity.id, "title": dialog.title, "username": None}
            )
        elif isinstance(entity, Channel) and entity.megagroup:
            groups.append(
                {
                    "group_id": entity.id,
                    "title": dialog.title,
                    "username": getattr(entity, "username", None),
                }
            )
    return groups


async def ensure_membership(
    session_string: str, phone: str, group_id: int, username: str | None = None
) -> bool:
    try:
        client = await get_or_create_client(session_string, phone)
        if username:
            entity = await client.get_entity(username)
        else:
            from telethon.tl.types import PeerChannel, PeerChat

            try:
                entity = await client.get_entity(PeerChannel(group_id))
            except Exception:
                entity = await client.get_entity(PeerChat(group_id))
        try:
            await client(JoinChannelRequest(entity))
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error(f"ensure_membership xatosi {phone} -> {group_id}: {e}")
        return False


async def send_message_to_group(
    session_string: str,
    phone: str,
    group_id: int,
    message: str,
    username: str | None = None,
):
    client = await get_or_create_client(session_string, phone)
    if username:
        entity = await client.get_entity(username)
    else:
        from telethon.tl.types import PeerChannel, PeerChat

        try:
            entity = await client.get_entity(PeerChannel(group_id))
        except Exception:
            entity = await client.get_entity(PeerChat(group_id))
    await client.send_message(entity, message)


async def add_group_by_username(
    session_string: str, phone: str, username_or_link: str
) -> dict:
    clean = username_or_link.strip().split("/")[-1].replace("@", "").strip()
    if not clean:
        raise ValueError("Username noto'g'ri kiritildi.")

    client = await get_or_create_client(session_string, phone)
    entity = await client.get_entity(clean)

    group_id = entity.id
    title = getattr(entity, "title", clean)
    username = getattr(entity, "username", clean)

    try:
        await client(JoinChannelRequest(entity))
    except Exception:
        pass

    return {
        "group_id": group_id,
        "title": title,
        "username": username,
    }