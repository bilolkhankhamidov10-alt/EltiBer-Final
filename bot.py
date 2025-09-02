from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
import asyncio

# ================== SOZLAMALAR ==================
TOKEN = "8305786670:AAEjM82HC3Yqat9-Bft2tlVic1PYUSAW5Ck"    # BotFather’dan token
DRIVERS_CHAT_ID = -4917715168                                # Haydovchilar guruhi ID

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================== XOTIRA (RAM) ==================
# Foydalanuvchi profillari: {user_id: {"name": str, "phone": str}}
user_profiles = {}

# Draftlar: {customer_id: {"stage": "region"|"city"|"vehicle"|"from"|"to",
#                          "region": str|None, "city": str|None,
#                          "vehicle": str|None, "from": str|None, "to": str|None}}
drafts = {}

# Aktiv buyurtmalar: {customer_id: {"region": str, "city": str, "vehicle": str, "from": str, "to": str, "msg_id": int}}
orders = {}

# (ixtiyoriy) Haydovchi ↔ mijoz bog‘lanishi
driver_links = {}

# ================== LABELLAR ==================
CANCEL = "❌ Bekor qilish"
BACK   = "◀️ Ortga"

# ================== MA’LUMOTLAR: Viloyat va shahar/tumanlar ==================
# Qisqartirilgan namunaviy ro‘yxat. Foydalanuvchi ro‘yxatda yo‘q joyni ham qo‘lda yozishi mumkin.
REGION_LIST = [
    "Toshkent sh.", "Toshkent vil.", "Andijon", "Farg‘ona", "Namangan",
    "Samarqand", "Buxoro", "Navoiy", "Qashqadaryo", "Surxondaryo",
    "Jizzax", "Sirdaryo", "Xorazm", "Qoraqalpog‘iston"
]

REGION_CITIES = {
    "Toshkent sh.": [
        "Chilonzor", "Yunusobod", "Yakkasaroy", "Mirobod", "Olmazor",
        "Shayxontohur", "Uchtepa", "Yashnobod", "Bektemir", "Sirg‘ali"
    ],
    "Toshkent vil.": [
        "Nurafshon", "Olmaliq", "Angren", "Chirchiq", "Bekobod",
        "Ohangaron", "Parkent", "Zangiota", "Piskent", "Bo‘ka", "Yangiyo‘l"
    ],
    "Farg‘ona": [
        "Farg‘ona sh.", "Qo‘qon", "Marg‘ilon", "Beshariq", "Quva",
        "Rishton", "Dang‘ara", "Oltiariq", "O‘zbekiston", "Yozyovon"
    ],
    "Andijon": [
        "Andijon sh.", "Asaka", "Xo‘jaobod", "Shahrixon", "Paxtaobod",
        "Baliqchi", "Marhamat", "Qorasuv", "Izboskan"
    ],
    "Namangan": [
        "Namangan sh.", "Chust", "Chortoq", "To‘raqo‘rg‘on", "Uchqo‘rg‘on",
        "Yangiqo‘rg‘on", "Pop", "Kosonsoy"
    ],
    "Samarqand": [
        "Samarqand sh.", "Kattaqo‘rg‘on", "Bulung‘ur", "Jomboy", "Ishtixon",
        "Tayloq", "Urgut", "Paxtachi"
    ],
    "Buxoro": [
        "Buxoro sh.", "G‘ijduvon", "Qorako‘l", "Vobkent", "Kogon", "Shofirkon"
    ],
    "Navoiy": [
        "Navoiy sh.", "Zarafshon", "Qiziltepa", "Konimex", "Nurota", "Uchquduq"
    ],
    "Qashqadaryo": [
        "Qarshi", "Shahrisabz", "Kitob", "Yakkabog‘", "Kasbi", "Koson", "G‘uzor", "Dehqonobod"
    ],
    "Surxondaryo": [
        "Termiz", "Denov", "Sherobod", "Boysun", "Jarqo‘rg‘on", "Qiziriq", "Sho‘rchi"
    ],
    "Jizzax": [
        "Jizzax sh.", "Zomin", "G‘allaorol", "Do‘stlik", "Paxtakor", "Forish"
    ],
    "Sirdaryo": [
        "Guliston", "Sirdaryo sh.", "Yangiyer", "Shirin", "Boyovut", "Oqoltin"
    ],
    "Xorazm": [
        "Urganch", "Xiva", "Shovot", "Xonqa", "Bog‘ot", "Gurlan"
    ],
    "Qoraqalpog‘iston": [
        "Nukus", "Taxiatosh", "Xo‘jayli", "Chimboy", "Mo‘ynoq", "Kegeyli"
    ]
}

# ================== KLAVIATURALAR ==================
def rows_from_list(items, per_row=3):
    return [list(map(lambda t: KeyboardButton(text=t), items[i:i+per_row])) for i in range(0, len(items), per_row)]

def keyboard_with_back_cancel(options, per_row=3, show_back=True):
    rows = rows_from_list(options, per_row=per_row)
    tail = []
    if show_back:
        tail.append(KeyboardButton(text=BACK))
    tail.append(KeyboardButton(text=CANCEL))
    rows.append(tail)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def region_keyboard():
    # Region bosqichida "Ortga" mantiqan yo‘q (bu start), lekin so‘ralganidek yonida ko‘rsatamiz; bosilsa qayta regionni ko‘rsatamiz.
    return keyboard_with_back_cancel(REGION_LIST, per_row=2, show_back=True)

def city_keyboard(region_name: str):
    cities = REGION_CITIES.get(region_name, [])
    if not cities:
        # Ro‘yxat bo‘lmasa, foydalanuvchi qo‘lda yozadi; faqat Ortga/Bekor ko‘rsatamiz
        return keyboard_with_back_cancel([], per_row=3, show_back=True)
    return keyboard_with_back_cancel(cities, per_row=3, show_back=True)

def vehicle_keyboard():
    VEHICLES = [
        "Labo", "Damas", "Gazel (bord)",
        "Van (damas)", "Isuzu (Katta)", "Isuzu (Kichik)",
        "Ref (muzlatkichli)", "Sprintor", "Vito", "Boshqa tur"
    ]
    return keyboard_with_back_cancel(VEHICLES, per_row=3, show_back=True)

def contact_keyboard(text="📲 Telefon raqamni yuborish"):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=text, request_contact=True)]],
        resize_keyboard=True
    )

def order_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🚖 Buyurtma berish")]],
        resize_keyboard=True
    )

# ================== 1) START: telefon BIR MARTA + buyurtma tugmasi ==================
@dp.message(CommandStart())
async def start_command(message: types.Message):
    uid = message.from_user.id
    profile = user_profiles.get(uid)

    if not profile or not profile.get("phone"):
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📞 Telefon raqamni yuborish", request_contact=True)]],
            resize_keyboard=True
        )
        await message.answer(
            f"Salom, {message.from_user.full_name}! 👋\n"
            "Iltimos, bir marta telefon raqamingizni yuboring:",
            reply_markup=kb
        )
    else:
        await message.answer(
            f"Xush kelibsiz, {profile['name']}!\n"
            "Buyurtma berishingiz mumkin 👇",
            reply_markup=order_keyboard()
        )

@dp.message(F.contact)
async def contact_received(message: types.Message):
    phone = message.contact.phone_number
    uid = message.from_user.id

    user_profiles[uid] = {"name": message.from_user.full_name, "phone": phone}
    await message.answer("✅ Telefon raqamingiz saqlandi.", reply_markup=types.ReplyKeyboardRemove())
    await message.answer("Endi buyurtma bera olasiz 👇", reply_markup=order_keyboard())

# ================== 2) BUYURTMA: (viloyat → shahar/tuman → mashina → qayerdan → qayerga) ==================
@dp.message(Command("buyurtma"))
async def buyurtma_cmd(message: types.Message):
    await prompt_order_flow(message)

@dp.message(F.text == "🚖 Buyurtma berish")
async def buyurtma_btn(message: types.Message):
    await prompt_order_flow(message)

async def prompt_order_flow(message: types.Message):
    uid = message.from_user.id
    profile = user_profiles.get(uid)

    if not profile or not profile.get("phone"):
        await message.answer("Iltimos, telefon raqamingizni yuboring 📞", reply_markup=contact_keyboard())
        return

    drafts[uid] = {"stage": "region", "region": None, "city": None, "vehicle": None, "from": None, "to": None}
    await message.answer("🗺 Iltimos, viloyatingizni tanlang:", reply_markup=region_keyboard())

@dp.message(F.text == CANCEL)
async def cancel_flow(message: types.Message):
    uid = message.from_user.id
    if uid in drafts:
        del drafts[uid]
    await message.answer("❌ Buyurtma bekor qilindi.", reply_markup=order_keyboard())

@dp.message(F.text == BACK)
async def back_flow(message: types.Message):
    uid = message.from_user.id
    d = drafts.get(uid)
    if not d:
        return

    stage = d["stage"]

    # Ortga mantiqi: region<-start (qayta region), city<-region, vehicle<-city, from<-vehicle, to<-from
    if stage == "region":
        # Startga qaytganday — yana regionni ko‘rsatamiz
        await message.answer("🗺 Iltimos, viloyatingizni tanlang:", reply_markup=region_keyboard())
        return

    if stage == "city":
        d["stage"] = "region"
        await message.answer("🗺 Viloyatni qayta tanlang:", reply_markup=region_keyboard())
        return

    if stage == "vehicle":
        d["stage"] = "city"
        region = d["region"] or ""
        await message.answer("🏙 Shahar/tumaningizni tanlang yoki yozing:", reply_markup=city_keyboard(region))
        return

    if stage == "from":
        d["stage"] = "vehicle"
        await message.answer("🚚 Qanday yuk mashinasi kerak?", reply_markup=vehicle_keyboard())
        return

    if stage == "to":
        d["stage"] = "from"
        await message.answer("📍 Yuk qayerdan olinadi? Manzilni yozing:", reply_markup=keyboard_with_back_cancel([], show_back=True))
        return

@dp.message(F.text)
async def collect_flow(message: types.Message):
    uid = message.from_user.id
    if uid not in drafts:
        return

    d = drafts[uid]
    stage = d["stage"]
    text = message.text.strip()

    # 2.1) VILOYAT
    if stage == "region":
        if text not in REGION_LIST:
            # ro‘yxatdan tashqarisi bo‘lsa ham qabul qilamiz
            d["region"] = text
        else:
            d["region"] = text

        d["stage"] = "city"
        await message.answer("🏙 Shahar/tumaningizni tanlang yoki yozing:", reply_markup=city_keyboard(d["region"]))
        return

    # 2.2) SHAHR/TUMAN
    if stage == "city":
        # ro‘yxatda bo‘lsa ham, bo‘lmasa ham qabul qilamiz
        d["city"] = text if text else "—"
        d["stage"] = "vehicle"
        await message.answer(
            "🚚 Qanday yuk mashinasi kerak?\nQuyidagidan tanlang yoki yozing:",
            reply_markup=vehicle_keyboard()
        )
        return

    # 2.3) MASHINA TURI
    if stage == "vehicle":
        d["vehicle"] = text if text else "Noma'lum"
        d["stage"] = "from"
        await message.answer(
            "📍 Yuk **qayerdan** olinadi? Manzilni yozing:",
            reply_markup=keyboard_with_back_cancel([], show_back=True)
        )
        return

    # 2.4) QAYERDAN
    if stage == "from":
        d["from"] = text
        d["stage"] = "to"
        await message.answer(
            "📦 Yuk **qayerga** yetkaziladi? Manzilni yozing:",
            reply_markup=keyboard_with_back_cancel([], show_back=True)
        )
        return

    # 2.5) QAYERGA → GURUHGА JO'NATAMIZ
    if stage == "to":
        d["to"] = text

        profile = user_profiles.get(uid, {"name": message.from_user.full_name})
        region, city, vehicle, pickup, dropoff = d["region"], d["city"], d["vehicle"], d["from"], d["to"]

        # Guruhga buyurtma (telefonsiz), “Qabul qilish” tugmasi bilan
        ikb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❗️ Qabul qilish", callback_data=f"accept_{uid}")]
        ])

        text_g = (
            f"📦 Yangi buyurtma!\n"
            f"👤 Mijoz: {profile['name']}\n"
            f"🗺 Viloyat: {region}\n"
            f"🏙 Shahar/Tuman: {city}\n"
            f"🚚 Mashina: {vehicle}\n"
            f"➡️ Yo‘nalish:\n"
            f"   • Qayerdan: {pickup}\n"
            f"   • Qayerga: {dropoff}\n"
            f"ℹ️ Telefon raqami guruhda ko‘rsatilmaydi."
        )
        sent = await bot.send_message(DRIVERS_CHAT_ID, text_g, reply_markup=ikb)

        orders[uid] = {
            "region": region, "city": city,
            "vehicle": vehicle, "from": pickup, "to": dropoff,
            "msg_id": sent.message_id
        }
        del drafts[uid]

        await message.answer("✅ Buyurtma haydovchilarga yuborildi. Javob kuting.", reply_markup=order_keyboard())
        return

# ================== 3) QABUL QILISH (DM → muvaffaqiyat bo'lsa postni o‘chirish) ==================
@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(callback: types.CallbackQuery):
    try:
        customer_id = int(callback.data.split("_")[1])
    except Exception:
        await callback.answer("Xato ID.", show_alert=True)
        return

    order = orders.get(customer_id)
    customer = user_profiles.get(customer_id)
    if not order or not customer:
        await callback.answer("Bu buyurtma topilmadi yoki allaqachon qabul qilingan.", show_alert=True)
        return

    driver_id = callback.from_user.id
    driver = user_profiles.get(driver_id)

    # Haydovchi telefonini oldindan tekshiramiz
    if not driver or not driver.get("phone"):
        await bot.send_message(
            driver_id,
            "ℹ️ Buyurtmani qabul qilishdan oldin telefon raqamingizni yuboring.",
            reply_markup=contact_keyboard()
        )
        await callback.answer("Avval telefon raqamingizni yuboring.", show_alert=True)
        return

    customer_name, customer_phone = customer.get("name", "Noma'lum"), customer.get("phone", "—")
    driver_name, driver_phone = driver.get("name", callback.from_user.full_name), driver.get("phone", "—")

    # 1) Avval haydovchiga DM: mijoz tafsilotlari
    txt_drv = (
        f"✅ Buyurtma sizga biriktirildi\n\n"
        f"👤 Mijoz: {customer_name}\n"
        f"📞 Telefon: {customer_phone}\n"
        f"🗺 Viloyat: {order['region']}\n"
        f"🏙 Shahar/Tuman: {order['city']}\n"
        f"🚚 Mashina: {order['vehicle']}\n"
        f"➡️ Yo‘nalish:\n"
        f"   • Qayerdan: {order['from']}\n"
        f"   • Qayerga: {order['to']}\n"
        f"🔗 Profil: tg://user?id={customer_id}"
    )
    try:
        await bot.send_message(driver_id, txt_drv)
    except Exception:
        await callback.answer("Haydovchiga DM yuborilmadi. Botga /start yozing.", show_alert=True)
        return

    # 2) DM muvaffaqiyatli bo‘lsa → buyurtmani yopamiz va postni o‘chiramiz
    accepted_order = orders.pop(customer_id)
    driver_links[driver_id] = customer_id

    try:
        await bot.delete_message(chat_id=DRIVERS_CHAT_ID, message_id=accepted_order["msg_id"])
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass

    # 3) Mijozga haydovchi ma’lumoti darhol
    txt_cust = (
        f"🚚 Buyurtmangizni haydovchi qabul qildi.\n\n"
        f"👨‍✈️ Haydovchi: {driver_name}\n"
        f"📞 Telefon: {driver_phone}\n"
        f"🔗 Profil: tg://user?id={driver_id}"
    )
    try:
        await bot.send_message(customer_id, txt_cust)
    except Exception:
        pass

    await callback.answer("Buyurtma sizga biriktirildi!")

# ================== 4) POLLING (konfliktsiz) ==================
async def main():
    print("Bot ishga tushmoqda...")
    # webhook bo'lsa o'chirish va kutib turgan updatelarni tashlash
    await bot.delete_webhook(drop_pending_updates=True)
    # aiogram 3: faqat kerakli update turlari
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
