# Türkiye Deprem MCP Sunucusu

Claude'a Türkiye'deki depremleri soran bir MCP (Model Context Protocol) sunucusu.
Veriler **AFAD**'dan anlık çekilir. AFAD cevap vermezse **Kandilli Rasathanesi** yedek kaynak olarak kullanılır.

**Hazırlayan:** Beyzanur Rana Sansar
**Ders:** İnternet Programcılığı — Bingöl Üniversitesi, Bilgisayar Programcılığı

## Araçlar

| Araç | Ne yapar | Örnek soru |
|---|---|---|
| `son_depremler` | En son depremleri listeler | "Son 10 depremi getir" |
| `en_buyuk_depremler` | Son X günün en büyük depremleri | "Bu haftanın en büyük 5 depremi?" |
| `sehir_depremleri` | Bir ildeki depremler | "Bingöl'de son bir ayda deprem oldu mu?" |
| `deprem_istatistigi` | Sayı, büyüklük dağılımı, en aktif yerler | "Son 7 günün deprem istatistiği" |

## Kullanılan teknolojiler

- Python 3.11+
- [FastMCP](https://gofastmcp.com) — MCP sunucusu
- httpx — AFAD/Kandilli'den veri çekme
- FastMCP Gateway — yayınlama (hosting)

## Bilgisayarda çalıştırma

```bash
pip install -r requirements.txt
python server.py
```

Sunucu `http://localhost:8000/mcp` adresinde çalışır.

## Claude'a bağlama

Claude → Ayarlar → Bağlayıcılar → **Özel bağlayıcı ekle** → sunucu adresini yapıştır (`https://<sunucu-adi>.fastmcp.app/mcp`).
