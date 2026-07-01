# AIZU-CLI — CLI AI Agent untuk Termux

Agent AI yang jalan langsung di terminal Termux, dengan banner ala hacker.
Bisa ngobrol, baca/tulis file, lihat direktori, dan jalankan perintah shell.

Hanya butuh **Python standar** — tanpa pip install. Panggil dengan: `aizu`

## Backend yang didukung

Semua pakai format API OpenAI, tinggal pilih:

| Backend     | Biaya            | Butuh internet | Dapat API key di            |
|-------------|------------------|----------------|-----------------------------|
| `groq`      | Gratis (free tier) | Ya           | https://console.groq.com    |
| `gemini`    | Gratis (free tier) | Ya           | https://aistudio.google.com |
| `openai`    | Bayar            | Ya             | https://platform.openai.com |
| `openrouter`| Sebagian gratis  | Ya             | https://openrouter.ai       |
| `ollama`    | Gratis, offline  | Tidak          | (model lokal di HP)         |
| `custom`    | Tergantung       | Ya             | masukkan URL & key sendiri  |

### Provider custom

Pilih `custom` saat setup (atau ketik `/provider`). Alurnya:
1. Masukkan **base URL** API (kompatibel OpenAI, mis. `https://.../v1`)
2. Masukkan **API key**
3. Sistem **memvalidasi** endpoint. Bila gagal, kamu diminta ulangi URL.
4. Setelah valid, sistem **mencari otomatis daftar model** dari API tersebut.
   Pilih lewat nomor, atau `/cari <kata>` untuk filter biar tak capek scroll.

### Mode kerja

Ganti gaya jawaban dengan `/mode <nama>`:
- `chat` — asisten umum (default)
- `code` — fokus menulis & memperbaiki kode
- `ringkas` — jawaban sesingkat mungkin
- `shell` — utamakan perintah shell

Provider, model, dan mode aktif selalu terlihat di banner saat start.

## Cara pakai

### Pemilihan provider (otomatis saat pertama jalan)

Saat `aizu` dijalankan pertama kali (belum ada `config.json`), akan muncul
**menu pemilihan penyedia AI**. Tinggal pilih nomornya, masukkan API key, dan
pilih simpan — selanjutnya langsung dipakai tanpa nanya lagi.

Provider juga bisa diganti kapan saja di dalam chat dengan `/backend <nama>`.

### 1. Pilih backend & siapkan API key

Cara A — pakai environment variable (paling cepat):

```bash
export AGENT_BACKEND=groq
export AGENT_API_KEY='gsk_...'      # key dari console.groq.com
python agent.py
```

Cara B — pakai file config:

```bash
cp config.example.json config.json
# edit config.json, isi api_key kamu
python agent.py
```

### 2. Contoh sesi

```
kamu> buatkan file catatan.txt isinya daftar belanja
  ↳ menjalankan tool: write_file({'path': 'catatan.txt', 'content': '...'})
agent> Sudah kubuat catatan.txt berisi daftar belanja.

kamu> ada file apa aja di folder ini?
  ↳ menjalankan tool: list_dir({'path': '.'})
agent> Ada agent.py, tools.py, catatan.txt, ...
```

### Perintah slash (di dalam chat)

Semua pengaturan bisa diatur langsung saat chat dengan mengetik `/`:

| Perintah          | Fungsi                                            |
|-------------------|---------------------------------------------------|
| `/help`           | Tampilkan daftar perintah                         |
| `/config`         | Lihat pengaturan saat ini (key disensor)          |
| `/backend <nama>` | Ganti backend: groq, openai, gemini, openrouter, ollama |
| `/key <api-key>`  | Atur API key                                      |
| `/model <nama>`   | Atur nama model                                   |
| `/url <base-url>` | Atur base URL endpoint (opsional)                 |
| `/save`           | Simpan pengaturan ke `config.json`                |
| `/tools`          | Daftar tool yang bisa dipakai agent               |
| `/mode [nama]`    | Lihat/ganti mode: chat, code, ringkas, shell      |
| `/models [kata]`  | Cari & pilih model yang tersedia dari provider    |
| `/provider`       | Setup ulang provider custom (URL + key + model)   |
| `/reset`          | Hapus riwayat percakapan                          |
| `/keluar`         | Keluar dari agent                                 |

Contoh: cukup jalankan `aizu`, lalu di dalam chat ketik:

```
/backend groq
/key gsk_xxxxxxxx
/save
```

Setelah `/save`, pengaturan tersimpan dan otomatis dipakai saat `aizu` dijalankan lagi.

## Untuk Ollama (offline)

```bash
pkg install ollama        # jika belum
ollama serve &            # jalankan server lokal
ollama pull llama3.2:1b   # model kecil, cocok untuk HP
export AGENT_BACKEND=ollama
python agent.py
```

## Keamanan
- Perintah shell yang jelas berbahaya (mis. `rm -rf /`) otomatis ditolak.
- Tetap hati-hati: agent bisa menulis file & menjalankan perintah sesuai instruksi.
