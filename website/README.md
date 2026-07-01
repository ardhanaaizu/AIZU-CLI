# AIZU-CLI Website

Landing page untuk AIZU-CLI.

## Struktur

```
website/
├── index.html      # Landing page utama
├── install.sh      # Script installer
└── README.md       # File ini
```

## Deploy

### Option 1: GitHub Pages
1. Push folder `website/` ke branch `gh-pages`
2. Aktifkan GitHub Pages di repo settings
3. Akses di: `https://ardhanaaizu.github.io/AIZU-CLI/`

### Option 2: Netlify
1. Drag & drop folder `website/` ke [Netlify](https://app.netlify.com)
2. Atau connect ke GitHub repo
3. Set publish directory: `website`

### Option 3: Vercel
1. Import repo ke [Vercel](https://vercel.com)
2. Set root directory: `website`
3. Deploy

### Option 4: Nginx (Self-hosted)
```nginx
server {
    listen 80;
    server_name cli.aaizu.id;

    root /var/www/AIZU-CLI/website;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }

    location /install.sh {
        add_header Content-Type text/plain;
    }
}
```

### Option 5: Python Simple Server (Testing)
```bash
cd website
python3 -m http.server 8000
# Buka http://localhost:8000
```

## Custom Domain

### Cloudflare
1. Tambah domain `cli.aaizu.id`
2. Setup CNAME atau A record ke server kamu
3. Aktifkan SSL/TLS

### Local Testing
```bash
# Tambah ke /etc/hosts (Linux/Mac)
127.0.0.1 cli.aaizu.id

# Jalankan server
cd website
python3 -m http.server 80
# Buka http://cli.aaizu.id
```
