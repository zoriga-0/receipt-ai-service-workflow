import os, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
def f(size, bold=False): return ImageFont.truetype(BOLD if bold else FONT, size, index=1)  # index 1 = KR
W = 560

def receipt(title, lines, items, total, pay, footer_extra=(), currency="원", tax=True):
    rows = []
    rows.append(("title", title))
    for l in lines: rows.append(("small", l))
    rows.append(("rule", ""))
    rows.append(("head", ("품목", "수량", "금액")))
    for name, qty, amt in items: rows.append(("item", (name, qty, amt)))
    rows.append(("rule", ""))
    if tax and currency == "원":
        supply = round(total / 1.1); vat = total - supply
        rows.append(("kv", ("공급가액", f"{supply:,}")))
        rows.append(("kv", ("부가세", f"{vat:,}")))
    rows.append(("total", ("합계", f"{total:,}{currency}" if currency == "원" else f"{currency}{total:,.2f}")))
    rows.append(("rule", ""))
    for l in pay: rows.append(("small", l))
    for l in footer_extra: rows.append(("small", l))
    rows.append(("note", "※ 테스트용 가상 영수증 (실제 거래 아님)"))
    H = 60 + sum({"title": 56, "rule": 22, "total": 46}.get(k, 32) for k, _ in rows) + 40
    img = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(img); y = 40
    for k, v in rows:
        if k == "title":
            d.text((W // 2, y), v, font=f(30, True), fill="black", anchor="ma"); y += 56
        elif k == "small":
            d.text((40, y), v, font=f(19), fill="#222"); y += 32
        elif k == "rule":
            d.line((40, y + 10, W - 40, y + 10), fill="#999", width=1); y += 22
        elif k == "head":
            d.text((40, y), v[0], font=f(19, True), fill="black"); d.text((340, y), v[1], font=f(19, True), fill="black", anchor="ra")
            d.text((W - 40, y), v[2], font=f(19, True), fill="black", anchor="ra"); y += 32
        elif k == "item":
            d.text((40, y), v[0], font=f(20), fill="black"); d.text((340, y), str(v[1]), font=f(20), fill="black", anchor="ra")
            d.text((W - 40, y), v[2], font=f(20), fill="black", anchor="ra"); y += 32
        elif k == "kv":
            d.text((40, y), v[0], font=f(19), fill="#222"); d.text((W - 40, y), v[1], font=f(19), fill="#222", anchor="ra"); y += 32
        elif k == "total":
            d.text((40, y), v[0], font=f(26, True), fill="black"); d.text((W - 40, y), v[1], font=f(26, True), fill="black", anchor="ra"); y += 46
        elif k == "note":
            d.text((W // 2, y + 6), v, font=f(16), fill="#666", anchor="ma"); y += 32
    return img

def save(img, name, q=82): img.save(os.path.join(OUT, name), "JPEG", quality=q)

card = lambda d, t, no: [f"카드: 신한 ****-1234", f"승인번호: {no}", f"거래일시: {d} {t}"]
# 1 식당
save(receipt("한빛식당", ["사업자 000-00-00001", "광주 북구 테스트로 1"],
     [("김치찌개", 2, "16,000"), ("공기밥", 2, "2,000")], 18000, card("2026-11-02", "12:31", "30012345")), "01_식당.jpg")
# 2 카페
cafe = receipt("카페 소나무", ["사업자 000-00-00002", "광주 북구 테스트로 2"],
     [("아메리카노", 3, "13,500")], 13500, card("2026-11-03", "15:05", "30023456"))
save(cafe, "02_카페.jpg")
# 3 택시
save(receipt("가온택시", ["차량번호 00가0000", "운행: 용봉동 → 광주역"],
     [("운임", 1, "12,400")], 12400, card("2026-11-03", "21:47", "30034567"), tax=False), "03_택시.jpg")
# 4 마트 (식재료 + 종량제 봉투)
save(receipt("테스트마트 용봉점", ["사업자 000-00-00004", "광주 북구 테스트로 4"],
     [("삼겹살 1kg", 1, "19,800"), ("상추", 2, "3,200"), ("종량제봉투 20L", 1, "2,000")], 25000,
     card("2026-11-01", "18:20", "30045678")), "04_마트_MT장보기.jpg")
# 5 마트 + 개인 물품
save(receipt("테스트마트 용봉점", ["사업자 000-00-00004", "광주 북구 테스트로 4"],
     [("라면 5입", 2, "8,400"), ("생수 2L", 6, "5,400"), ("면도기", 1, "6,700")], 20500,
     card("2026-11-01", "18:42", "30056789")), "05_마트_개인물품섞임.jpg")
# 6 흐리고 기울어진 사진
blur = receipt("한빛식당", ["사업자 000-00-00001", "광주 북구 테스트로 1"],
     [("제육볶음", 3, "27,000")], 27000, card("2026-11-04", "12:10", "30067890"))
blur = blur.rotate(7, expand=True, fillcolor="#bbb").filter(ImageFilter.GaussianBlur(2.2))
blur = ImageEnhance.Brightness(blur).enhance(0.8)
save(blur, "06_흐린사진.jpg", q=60)
# 7 해외 (USD)
save(receipt("PINE COFFEE (NY)", ["Test St 7, New York", "TEST RECEIPT"],
     [("Latte", 2, "$11.00"), ("Muffin", 1, "$3.50")], 14.5, ["Card: VISA ****1234", "Auth: 70078901", "Date: 2026-10-28 09:14"],
     currency="$", tax=False), "07_해외_USD.jpg")
# 8 같은 카페 영수증을 다시 찍은 사진 (조금 돌리고 어둡게)
again = ImageEnhance.Brightness(cafe.rotate(-3, expand=True, fillcolor="#ddd")).enhance(0.92)
save(again, "08_카페_다시찍음.jpg", q=75)
# 9 날짜 오기 (미래 날짜)
save(receipt("한빛식당", ["사업자 000-00-00001", "광주 북구 테스트로 1"],
     [("된장찌개", 1, "8,000")], 8000, card("2027-03-01", "12:00", "30089012")), "09_미래날짜.jpg")
for n in sorted(os.listdir(OUT)): print(n, os.path.getsize(os.path.join(OUT, n)))
