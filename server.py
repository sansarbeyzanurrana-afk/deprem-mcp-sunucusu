"""
Türkiye Deprem MCP Sunucusu
---------------------------
Claude'a Türkiye'deki son depremleri getiren araçlar sağlar.

Veri kaynağı: AFAD (deprem.afad.gov.tr). AFAD cevap vermezse
Kandilli Rasathanesi (koeri.boun.edu.tr) listesi yedek olarak kullanılır.

Not: AFAD tek istekte en fazla 1000 deprem verir ve yalnızca yaklaşık
son 10-12 günün verisini sunar. Bu yüzden araçlar en fazla 10 gün geriye bakar.

Hazırlayan: Beyzanur Rana Sansar - Bingöl Üniversitesi, Bilgisayar Programcılığı
"""

import re
from collections import Counter
from datetime import datetime, timedelta, timezone

import httpx
from fastmcp import FastMCP

mcp = FastMCP(
    name="Türkiye Deprem",
    instructions=(
        "Türkiye ve çevresindeki depremleri AFAD verileriyle getirir. "
        "Saatler Türkiye saatidir (UTC+3)."
    ),
)

TR_SAAT = timezone(timedelta(hours=3))
MAKS_GUN = 10  # AFAD yaklaşık son 10-12 günü verdiği için
AFAD_URL = "https://servisnet.afad.gov.tr/apigateway/deprem/apiv2/event/filter"
KANDILLI_URL = "http://www.koeri.boun.edu.tr/scripts/lst0.asp"


# ----------------------------------------------------------------------
# Yardımcı fonksiyonlar
# ----------------------------------------------------------------------

def _sayi(deger, varsayilan=0.0):
    """Metin ya da sayıyı güvenli şekilde float'a çevirir."""
    try:
        return float(deger)
    except (TypeError, ValueError):
        return varsayilan


def _sade(metin: str) -> str:
    """Türkçe karakterleri sadeleştirip küçük harfe çevirir (arama için)."""
    metin = (metin or "").replace("I", "ı").replace("İ", "i").lower()
    tablo = str.maketrans("çğıöşüâî", "cgiosuai")
    return metin.translate(tablo)


def _afad_getir(gun: int, limit: int = 1000) -> list[dict]:
    """AFAD'dan son `gun` günün depremlerini getirir (yeniden eskiye)."""
    simdi = datetime.now(timezone.utc)
    baslangic = simdi - timedelta(days=gun)
    parametreler = {
        "start": baslangic.strftime("%Y-%m-%d %H:%M:%S"),
        "end": simdi.strftime("%Y-%m-%d %H:%M:%S"),
        "orderby": "timedesc",
        "limit": limit,
        "format": "json",
    }
    cevap = httpx.get(AFAD_URL, params=parametreler, timeout=20, follow_redirects=True)
    cevap.raise_for_status()

    depremler = []
    for k in cevap.json():
        # AFAD zamanları UTC verir, Türkiye saatine çeviriyoruz.
        zaman = datetime.fromisoformat(str(k["date"]).replace("Z", ""))
        zaman = zaman.replace(tzinfo=timezone.utc).astimezone(TR_SAAT)
        il = k.get("province") or ""
        ilce = k.get("district") or ""
        yer = f"{il} - {ilce}" if il and ilce else (k.get("location") or il or "Bilinmiyor")
        depremler.append({
            "zaman": zaman,
            "yer": yer,
            "il": il,
            "buyukluk": _sayi(k.get("magnitude")),
            "derinlik": _sayi(k.get("depth")),
            "enlem": _sayi(k.get("latitude")),
            "boylam": _sayi(k.get("longitude")),
        })
    return depremler


def _kandilli_getir() -> list[dict]:
    """Kandilli'nin son 500 deprem listesini getirir (yedek kaynak)."""
    cevap = httpx.get(KANDILLI_URL, timeout=20, follow_redirects=True)
    cevap.raise_for_status()
    metin = cevap.content.decode("windows-1254", errors="replace")

    satir_kalibi = re.compile(
        r"^(\d{4}\.\d{2}\.\d{2}) (\d{2}:\d{2}:\d{2})\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
        r"\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+?)\s{2,}"
    )
    depremler = []
    for satir in metin.splitlines():
        m = satir_kalibi.match(satir)
        if not m:
            continue
        tarih, saat, enlem, boylam, derinlik, md, ml, mw, yer = m.groups()
        # Önce ML, yoksa Mw, o da yoksa MD büyüklüğünü kullan.
        buyukluk = next((_sayi(x) for x in (ml, mw, md) if x != "-.-"), 0.0)
        il_eslesme = re.search(r"\(([^)]+)\)", yer)
        depremler.append({
            "zaman": datetime.strptime(f"{tarih} {saat}", "%Y.%m.%d %H:%M:%S").replace(tzinfo=TR_SAAT),
            "yer": yer.strip(),
            "il": il_eslesme.group(1) if il_eslesme else "",
            "buyukluk": buyukluk,
            "derinlik": _sayi(derinlik),
            "enlem": _sayi(enlem),
            "boylam": _sayi(boylam),
        })
    return depremler


def _depremleri_getir(gun: int) -> tuple[list[dict], str]:
    """Önce AFAD'ı, olmazsa Kandilli'yi dener. (depremler, kaynak) döndürür."""
    sinir = datetime.now(TR_SAAT) - timedelta(days=gun)
    try:
        depremler, kaynak = _afad_getir(gun), "AFAD"
    except Exception:
        depremler, kaynak = _kandilli_getir(), "Kandilli Rasathanesi"
    # Tarih aralığının dışındakileri ele, en yeniden eskiye sırala.
    depremler = [d for d in depremler if d["zaman"] >= sinir]
    depremler.sort(key=lambda d: d["zaman"], reverse=True)
    return depremler, kaynak


def _bicimle(d: dict) -> dict:
    """Bir depremi Claude'a gönderilecek sade sözlüğe çevirir."""
    return {
        "tarih_saat": d["zaman"].strftime("%d.%m.%Y %H:%M:%S"),
        "yer": d["yer"],
        "buyukluk": round(d["buyukluk"], 1),
        "derinlik_km": round(d["derinlik"], 1),
        "enlem": d["enlem"],
        "boylam": d["boylam"],
    }


def _sinirla(deger: int, en_az: int, en_cok: int) -> int:
    return max(en_az, min(en_cok, int(deger)))


# ----------------------------------------------------------------------
# MCP araçları
# ----------------------------------------------------------------------

@mcp.tool
def son_depremler(adet: int = 10, min_buyukluk: float = 0.0) -> dict:
    """Türkiye'de meydana gelen en son depremleri getirir (yeniden eskiye).

    Args:
        adet: Kaç deprem gösterilsin (1-100). Varsayılan 10.
        min_buyukluk: Bu büyüklüğün altındaki depremleri gösterme. Varsayılan 0.
    """
    adet = _sinirla(adet, 1, 100)
    depremler, kaynak = _depremleri_getir(gun=2)
    secilen = [d for d in depremler if d["buyukluk"] >= min_buyukluk][:adet]
    return {
        "kaynak": kaynak,
        "deprem_sayisi": len(secilen),
        "depremler": [_bicimle(d) for d in secilen],
    }


@mcp.tool
def en_buyuk_depremler(gun: int = 7, adet: int = 10) -> dict:
    """Son X gün içindeki en büyük depremleri büyükten küçüğe sıralar.

    Args:
        gun: Kaç gün geriye bakılsın (1-10). Varsayılan 7.
        adet: Kaç deprem gösterilsin (1-50). Varsayılan 10.
    """
    gun = _sinirla(gun, 1, MAKS_GUN)
    adet = _sinirla(adet, 1, 50)
    depremler, kaynak = _depremleri_getir(gun=gun)
    secilen = sorted(depremler, key=lambda d: d["buyukluk"], reverse=True)[:adet]
    return {
        "kaynak": kaynak,
        "donem": f"Son {gun} gün",
        "depremler": [_bicimle(d) for d in secilen],
    }


@mcp.tool
def sehir_depremleri(sehir: str, gun: int = 10, adet: int = 20) -> dict:
    """Belirli bir ilde (veya yer adında) son X gündeki depremleri getirir (en fazla 10 gün).

    Args:
        sehir: İl ya da yer adı, örn. "Bingöl", "İzmir", "Ege Denizi".
        gun: Kaç gün geriye bakılsın (1-10). Varsayılan 10.
        adet: En fazla kaç deprem gösterilsin (1-100). Varsayılan 20.
    """
    gun = _sinirla(gun, 1, MAKS_GUN)
    adet = _sinirla(adet, 1, 100)
    aranan = _sade(sehir)
    depremler, kaynak = _depremleri_getir(gun=gun)
    bulunan = [d for d in depremler if aranan in _sade(d["il"]) or aranan in _sade(d["yer"])]
    return {
        "kaynak": kaynak,
        "sehir": sehir,
        "donem": f"Son {gun} gün",
        "toplam_deprem": len(bulunan),
        "en_buyuk": _bicimle(max(bulunan, key=lambda d: d["buyukluk"])) if bulunan else None,
        "depremler": [_bicimle(d) for d in bulunan[:adet]],
    }


@mcp.tool
def deprem_istatistigi(gun: int = 7) -> dict:
    """Son X günün deprem istatistiklerini çıkarır: toplam sayı,
    büyüklük dağılımı, en çok deprem olan iller ve en büyük deprem.

    Args:
        gun: Kaç gün geriye bakılsın (1-10). Varsayılan 7.
    """
    gun = _sinirla(gun, 1, MAKS_GUN)
    depremler, kaynak = _depremleri_getir(gun=gun)
    if not depremler:
        return {"kaynak": kaynak, "donem": f"Son {gun} gün", "toplam_deprem": 0}

    araliklar = {"0-2": 0, "2-3": 0, "3-4": 0, "4-5": 0, "5 ve üzeri": 0}
    for d in depremler:
        b = d["buyukluk"]
        if b < 2:
            araliklar["0-2"] += 1
        elif b < 3:
            araliklar["2-3"] += 1
        elif b < 4:
            araliklar["3-4"] += 1
        elif b < 5:
            araliklar["4-5"] += 1
        else:
            araliklar["5 ve üzeri"] += 1

    iller = Counter(d["il"] or d["yer"] for d in depremler)
    buyuklukler = [d["buyukluk"] for d in depremler]
    return {
        "kaynak": kaynak,
        "donem": f"Son {gun} gün",
        "toplam_deprem": len(depremler),
        "not": "AFAD en fazla 1000 kayıt verdiği için toplam eksik olabilir." if len(depremler) >= 1000 else None,
        "ortalama_buyukluk": round(sum(buyuklukler) / len(buyuklukler), 2),
        "buyukluk_dagilimi": araliklar,
        "en_cok_deprem_olan_yerler": [{"yer": y, "sayi": s} for y, s in iller.most_common(5)],
        "en_buyuk_deprem": _bicimle(max(depremler, key=lambda d: d["buyukluk"])),
    }


if __name__ == "__main__":
    # Bilgisayarında denemek için: python server.py
    mcp.run(transport="http", host="0.0.0.0", port=8000)
