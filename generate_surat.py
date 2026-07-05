#!/usr/bin/env python3
"""
generate_surat.py — Generator surat lamaran kerja PDF untuk AIZU-CLI.

Menggunakan reportlab untuk generate PDF surat lamaran + lampiran dokumen.

Usage:
    from generate_surat import generate_surat_lamaran
    result = generate_surat_lamaran(posisi, perusahaan, user_data)
"""

import os
import time
from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, Image, HRFlowable
    )
    from reportlab.lib import colors
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 2.5 * cm

WARNA_PRIMER = HexColor("#1a1a2e")
WARNA_SEKUNDER = HexColor("#16213e")
WARNA_AKSEN = HexColor("#0f3460")
WARNA_TEXT = HexColor("#2c2c2c")
WARNA_ABU = HexColor("#666666")
WARNA_LIGHT = HexColor("#f0f0f0")


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
def _get_styles():
    """Buat custom paragraph styles."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name='SuratKop',
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        alignment=TA_CENTER,
        textColor=WARNA_PRIMER,
    ))

    styles.add(ParagraphStyle(
        name='SuratKopSub',
        fontName='Helvetica',
        fontSize=10,
        leading=13,
        alignment=TA_CENTER,
        textColor=WARNA_ABU,
    ))

    styles.add(ParagraphStyle(
        name='SuratBody',
        fontName='Helvetica',
        fontSize=11,
        leading=16,
        alignment=TA_JUSTIFY,
        textColor=WARNA_TEXT,
        spaceAfter=6,
    ))

    styles.add(ParagraphStyle(
        name='SuratBodyBold',
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=16,
        alignment=TA_LEFT,
        textColor=WARNA_TEXT,
    ))

    styles.add(ParagraphStyle(
        name='SuratJudul',
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=18,
        alignment=TA_CENTER,
        textColor=WARNA_PRIMER,
        spaceAfter=12,
    ))

    styles.add(ParagraphStyle(
        name='SuratTanggal',
        fontName='Helvetica',
        fontSize=11,
        leading=14,
        alignment=TA_RIGHT,
        textColor=WARNA_TEXT,
    ))

    styles.add(ParagraphStyle(
        name='SuratLampiran',
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        alignment=TA_LEFT,
        textColor=WARNA_PRIMER,
        spaceBefore=12,
        spaceAfter=8,
    ))

    styles.add(ParagraphStyle(
        name='SuratTableHeader',
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=white,
    ))

    styles.add(ParagraphStyle(
        name='SuratTableCell',
        fontName='Helvetica',
        fontSize=10,
        leading=13,
        textColor=WARNA_TEXT,
    ))

    return styles


# ---------------------------------------------------------------------------
# Header & Footer
# ---------------------------------------------------------------------------
def _header_footer(canvas, doc):
    """Draw header line dan footer page number."""
    canvas.saveState()

    # Header line
    canvas.setStrokeColor(WARNA_AKSEN)
    canvas.setLineWidth(1.5)
    canvas.line(MARGIN, PAGE_HEIGHT - MARGIN + 0.3*cm, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - MARGIN + 0.3*cm)

    # Footer
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(WARNA_ABU)
    canvas.drawCentredString(PAGE_WIDTH / 2, MARGIN - 1*cm, f"Halaman {doc.page}")

    canvas.restoreState()


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------
def generate_surat_lamaran(posisi: str, perusahaan: str, user_data: dict,
                           tujuan: str = None, output_dir: str = None) -> dict:
    """Generate surat lamaran kerja dalam format PDF.

    Args:
        posisi: Posisi yang dilamar (mis: "Backend Developer")
        perusahaan: Nama perusahaan (mis: "PT ABC Indonesia")
        user_data: Dict data user dari UserDataManager.get_full_profile()
        tujuan: Tujuan surat (mis: "HRD Manager" atau nama orang). Default: "HRD Manager"
        output_dir: Folder output. Default: data_folder user

    Returns:
        dict: Status dengan path file PDF yang dihasilkan.
    """
    if not HAS_REPORTLAB:
        return {"success": False, "error": "library reportlab belum di-install. Jalankan: pip install reportlab"}

    profil = user_data.get("profil", {})
    nama = profil.get("nama_lengkap", "Nama Tidak Diketahui")
    if not tujuan:
        tujuan = "HRD Manager"

    # Output path
    if not output_dir:
        output_dir = user_data.get("data_folder", os.path.expanduser("~"))
    os.makedirs(output_dir, exist_ok=True)

    safe_nama = perusahaan.replace(" ", "-").replace(".", "")[:30]
    timestamp = datetime.now().strftime("%Y%m%d")
    filename = f"surat-lamaran-{safe_nama}-{timestamp}.pdf"
    output_path = os.path.join(output_dir, filename)

    # Build PDF
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )

    styles = _get_styles()
    story = []

    # === HALAMAN 1: SURAT LAMARAN ===

    # Kop surat
    story.append(Paragraph("SURAT LAMARAN KERJA", styles['SuratJudul']))
    story.append(Spacer(1, 0.5*cm))

    # Garis bawah judul
    story.append(HRFlowable(width="100%", thickness=2, color=WARNA_AKSEN, spaceAfter=0.5*cm))

    # Tanggal
    bulan_indo = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
                  "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    now = datetime.now()
    tanggal = f"{now.day} {bulan_indo[now.month-1]} {now.year}"
    story.append(Paragraph(f"Jakarta, {tanggal}", styles['SuratTanggal']))
    story.append(Spacer(1, 0.5*cm))

    # Kepada
    story.append(Paragraph(f"Kepada Yth.", styles['SuratBody']))
    story.append(Paragraph(f"<b>{tujuan}</b>", styles['SuratBody']))
    story.append(Paragraph(f"di {perusahaan}", styles['SuratBody']))
    story.append(Paragraph("di Tempat", styles['SuratBody']))
    story.append(Spacer(1, 0.5*cm))

    # Salam pembuka
    story.append(Paragraph("Dengan hormat,", styles['SuratBody']))
    story.append(Spacer(1, 0.3*cm))

    # Isi surat
    alamat = profil.get("alamat", "")
    no_hp = profil.get("no_hp", "")
    email = profil.get("email", "")

    # Paragraf 1: Perkenalan
    p1 = (
        f"Berdasarkan informasi yang saya peroleh mengenai lowongan pekerjaan "
        f"di {perusahaan}, dengan ini saya bermaksud mengajukan lamaran untuk "
        f"posisi <b>{posisi}</b>."
    )
    story.append(Paragraph(p1, styles['SuratBody']))

    # Paragraf 2: Data singkat
    pendidikan = user_data.get("pendidikan", [])
    pengalaman = user_data.get("pengalaman", [])
    keahlian = user_data.get("keahlian", [])

    edu_text = ""
    if pendidikan:
        latest = max(pendidikan, key=lambda p: int(p.get("tahun_lulus", "0") or "0"))
        edu_text = f" Saya merupakan lulusan {latest.get('jenjang', '?')} {latest.get('jurusan', '?')} dari {latest.get('institusi', '?')}."

    exp_text = ""
    if pengalaman:
        exp_years = len(pengalaman)
        exp_text = f" Saya memiliki pengalaman kerja sebanyak {exp_years} posisi di berbagai perusahaan."

    skill_text = ""
    if keahlian:
        top_skills = keahlian[:5]
        skill_text = f" Beberapa keahlian yang saya miliki antara lain: {', '.join(top_skills)}."

    p2 = f"Adapun data singkat mengenai diri saya sebagai berikut:{edu_text}{exp_text}{skill_text}"
    story.append(Paragraph(p2, styles['SuratBody']))

    # Paragraf 3: Data diri
    ttl = f"{profil.get('tempat_lahir', '-')}, {profil.get('tanggal_lahir', '-')}"
    data_rows = [
        ["Nama Lengkap", f": {nama}"],
        ["Tempat/Tgl Lahir", f": {ttl}"],
        ["Jenis Kelamin", f": {profil.get('jenis_kelamin', '-')}"],
        ["Alamat", f": {alamat}"],
        ["No. HP", f": {no_hp}"],
        ["Email", f": {email}"],
    ]

    table_data = [[Paragraph(r[0], styles['SuratTableCell']),
                    Paragraph(r[1], styles['SuratTableCell'])] for r in data_rows]
    t = Table(table_data, colWidths=[4.5*cm, 10*cm])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(Spacer(1, 0.3*cm))
    story.append(t)

    # Paragraf 4: Penutup
    story.append(Spacer(1, 0.3*cm))
    p4 = (
        "Besar harapan saya untuk dapat diterima bekerja di perusahaan yang Bapak/Ibu pimpin. "
        "Saya siap untuk menghadiri wawancara dan tes lainnya sesuai jadwal yang ditentukan. "
        "Atas perhatian dan kebijaksanaan Bapak/Ibu, saya ucapkan terima kasih."
    )
    story.append(Paragraph(p4, styles['SuratBody']))

    # Tanda tangan
    story.append(Spacer(1, 1.5*cm))
    story.append(Paragraph("Hormat saya,", styles['SuratBody']))
    story.append(Spacer(1, 2*cm))

    # Cek apakah ada foto tanda tangan
    foto_path = user_data.get("dokumen", {}).get("foto", "")
    data_folder = user_data.get("data_folder", "")
    if foto_path and data_folder:
        full_foto = os.path.join(data_folder, foto_path)
        if os.path.exists(full_foto):
            try:
                img = Image(full_foto, width=3*cm, height=3*cm)
                story.append(img)
            except Exception:
                story.append(Spacer(1, 1*cm))

    story.append(Paragraph(f"<b>{nama}</b>", styles['SuratBodyBold']))

    # === HALAMAN 2: LAMPIRAN DATA DIRI ===
    story.append(PageBreak())
    story.append(Paragraph("LAMPIRAN: DATA DIRI", styles['SuratJudul']))
    story.append(HRFlowable(width="100%", thickness=2, color=WARNA_AKSEN, spaceAfter=0.5*cm))

    # Biodata lengkap
    all_fields = [
        ("Nama Lengkap", profil.get("nama_lengkap", "-")),
        ("Tempat Lahir", profil.get("tempat_lahir", "-")),
        ("Tanggal Lahir", profil.get("tanggal_lahir", "-")),
        ("Jenis Kelamin", profil.get("jenis_kelamin", "-")),
        ("Kewarganegaraan", profil.get("kewarganegaraan", "Indonesia")),
        ("Agama", profil.get("agama", "-")),
        ("Status Pernikahan", profil.get("status_pernikahan", "-")),
        ("Alamat", profil.get("alamat", "-")),
        ("No. HP", profil.get("no_hp", "-")),
        ("Email", profil.get("email", "-")),
    ]

    story.append(Paragraph("<b>A. Biodata Diri</b>", styles['SuratLampiran']))
    table_data = [[Paragraph(f"<b>{f[0]}</b>", styles['SuratTableCell']),
                    Paragraph(f[1], styles['SuratTableCell'])] for f in all_fields]
    t = Table(table_data, colWidths=[4.5*cm, 10*cm])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('BACKGROUND', (0, 0), (0, -1), WARNA_LIGHT),
        ('GRID', (0, 0), (-1, -1), 0.5, WARNA_ABU),
    ]))
    story.append(t)

    # Pendidikan
    if pendidikan:
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph("<b>B. Riwayat Pendidikan</b>", styles['SuratLampiran']))
        header = ["No", "Jenjang", "Institusi", "Jurusan", "Tahun", "IPK"]
        rows = [header]
        for i, p in enumerate(pendidikan, 1):
            rows.append([
                str(i),
                p.get("jenjang", "-"),
                p.get("institusi", "-"),
                p.get("jurusan", "-"),
                f"{p.get('tahun_masuk', '?')}-{p.get('tahun_lulus', '?')}",
                p.get("ipk", "-"),
            ])
        table_data = [[Paragraph(str(c), styles['SuratTableCell']) for c in row] for row in rows]
        table_data[0] = [Paragraph(f"<b>{c}</b>", styles['SuratTableCell']) for c in header]
        t = Table(table_data, colWidths=[1*cm, 2*cm, 4*cm, 3.5*cm, 2.5*cm, 1.5*cm])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, 0), WARNA_AKSEN),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('GRID', (0, 0), (-1, -1), 0.5, WARNA_ABU),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ]))
        story.append(t)

    # Pengalaman kerja
    if pengalaman:
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph("<b>C. Pengalaman Kerja</b>", styles['SuratLampiran']))
        header = ["No", "Posisi", "Perusahaan", "Tahun", "Deskripsi"]
        rows = [header]
        for i, p in enumerate(pengalaman, 1):
            rows.append([
                str(i),
                p.get("posisi", "-"),
                p.get("perusahaan", "-"),
                f"{p.get('tahun_masuk', '?')}-{p.get('tahun_keluar', 'sekarang')}",
                p.get("deskripsi", "-")[:80],
            ])
        table_data = [[Paragraph(str(c), styles['SuratTableCell']) for c in row] for row in rows]
        table_data[0] = [Paragraph(f"<b>{c}</b>", styles['SuratTableCell']) for c in header]
        t = Table(table_data, colWidths=[1*cm, 3*cm, 3.5*cm, 2.5*cm, 4.5*cm])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BACKGROUND', (0, 0), (-1, 0), WARNA_AKSEN),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('GRID', (0, 0), (-1, -1), 0.5, WARNA_ABU),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ]))
        story.append(t)

    # Keahlian
    if keahlian:
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph("<b>D. Keahlian</b>", styles['SuratLampiran']))
        story.append(Paragraph(", ".join(keahlian), styles['SuratBody']))

    # Sertifikat
    sertifikat = user_data.get("sertifikat", [])
    if sertifikat:
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph("<b>E. Sertifikat</b>", styles['SuratLampiran']))
        for s in sertifikat:
            story.append(Paragraph(
                f"• {s.get('nama', '?')} — {s.get('penerbit', '?')} ({s.get('tahun', '?')})",
                styles['SuratBody']
            ))

    # Build PDF
    try:
        doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    except Exception as e:
        return {"success": False, "error": f"Gagal generate PDF: {e}"}

    # Hitung halaman
    from reportlab.lib.pagesizes import A4 as _A4
    page_count = 2 + len(sertifikat)  # Estimasi sederhana

    return {
        "success": True,
        "path": output_path,
        "filename": filename,
        "message": (
            f"✅ Surat lamaran berhasil di-generate!\n\n"
            f"📄 File: {filename}\n"
            f"📁 Lokasi: {output_path}\n"
            f"📋 Posisi: {posisi} di {perusahaan}\n"
            f"👤 Atas nama: {nama}"
        ),
    }


def check_reportlab() -> bool:
    """Cek apakah reportlab tersedia."""
    return HAS_REPORTLAB
