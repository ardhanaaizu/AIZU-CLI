#!/usr/bin/env python3
"""
user_data.py — Manajemen data profil user untuk AIZU-CLI.

Menyimpan data pribadi, pendidikan, pengalaman, keahlian, sertifikat, dan dokumen.
Data disimpan di folder yang dipilih user (tidak terekspos ke luar).

Usage:
    from user_data import get_user_data_manager
    mgr = get_user_data_manager()
"""

import json
import os
import shutil
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
AIZU_DIR = os.path.join(os.path.expanduser("~"), ".aizu")
PROFILE_FILE = os.path.join(AIZU_DIR, "user_data", "profile.json")

FIELD_LABELS = {
    "nama_lengkap": "Nama Lengkap",
    "tempat_lahir": "Tempat Lahir",
    "tanggal_lahir": "Tanggal Lahir",
    "jenis_kelamin": "Jenis Kelamin",
    "alamat": "Alamat Lengkap",
    "no_hp": "No. HP",
    "email": "Email",
    "agama": "Agama",
    "status_pernikahan": "Status Pernikahan",
    "kewarganegaraan": "Kewarganegaraan",
}

DOKUMEN_LABELS = {
    "foto": "Foto Profil",
    "ijazah": "Ijazah",
    "cv": "CV / Resume",
    "transkrip": "Transkrip Nilai",
    "ktp": "KTP",
    "skck": "SKCK",
    "surat_pengalaman": "Surat Pengalaman Kerja",
    "sertifikat_kompetensi": "Sertifikat Kompetensi",
    "lainnya": "Dokumen Lainnya",
}


# ---------------------------------------------------------------------------
# UserDataManager
# ---------------------------------------------------------------------------
class UserDataManager:
    """Manajemen data profil user."""

    def __init__(self, data_folder=None):
        """Inisialisasi manager.

        Args:
            data_folder: Path folder tempat menyimpan data user.
                         Jika None, akan di-setup dari profile.json.
        """
        os.makedirs(os.path.dirname(PROFILE_FILE), exist_ok=True)
        self.profile = self._load_profile()
        if data_folder:
            self.profile["data_folder"] = data_folder
            self._save_profile()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def is_setup(self) -> bool:
        """Cek apakah user sudah setup data folder."""
        return self.profile.get("setup", False)

    def setup(self, folder_path: str) -> dict:
        """Setup data folder dan inisialisasi profil.

        Args:
            folder_path: Path ke folder data user.

        Returns:
            dict: Status setup.
        """
        folder_path = os.path.abspath(os.path.expanduser(folder_path))

        # Validasi folder
        if not os.path.exists(folder_path):
            try:
                os.makedirs(folder_path, exist_ok=True)
            except OSError as e:
                return {"success": False, "error": f"Tidak bisa membuat folder: {e}"}

        # Buat subfolder
        subfolders = ["foto", "dokumen", "sertifikat", "ijazah", "cv"]
        for sf in subfolders:
            os.makedirs(os.path.join(folder_path, sf), exist_ok=True)

        self.profile["data_folder"] = folder_path
        self.profile["setup"] = True
        self.profile["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save_profile()

        return {
            "success": True,
            "folder": folder_path,
            "subfolders": subfolders,
            "message": f"✅ Data folder berhasil di-setup di:\n   {folder_path}\n\n"
                       f"Subfolder yang dibuat: {', '.join(subfolders)}"
        }

    # ------------------------------------------------------------------
    # Profil
    # ------------------------------------------------------------------
    def get_profil(self) -> dict:
        """Ambil data profil."""
        return self.profile.get("profil", {})

    def get_full_profile(self) -> dict:
        """Ambil seluruh data (profil + pendidikan + pengalaman + dll)."""
        return self.profile

    def edit_profil(self, field: str, value: str) -> dict:
        """Edit satu field profil.

        Args:
            field: Nama field (nama_lengkap, alamat, dll)
            value: Nilai baru

        Returns:
            dict: Status edit.
        """
        if field not in FIELD_LABELS:
            return {
                "success": False,
                "error": f"Field '{field}' tidak valid. Field yang tersedia: {', '.join(FIELD_LABELS.keys())}"
            }

        if "profil" not in self.profile:
            self.profile["profil"] = {}

        old_value = self.profile["profil"].get(field, "")
        self.profile["profil"][field] = value
        self._save_profile()

        return {
            "success": True,
            "field": FIELD_LABELS[field],
            "old": old_value,
            "new": value,
            "message": f"✅ {FIELD_LABELS[field]} diubah dari '{old_value}' ke '{value}'"
        }

    def edit_profil_bulk(self, data: dict) -> dict:
        """Edit beberapa field profil sekaligus.

        Args:
            data: dict {field: value, ...}

        Returns:
            dict: Status edit.
        """
        updated = []
        for field, value in data.items():
            if field in FIELD_LABELS:
                self.profile.setdefault("profil", {})[field] = value
                updated.append(FIELD_LABELS[field])
        if updated:
            self._save_profile()
        return {
            "success": bool(updated),
            "updated": updated,
            "message": f"✅ {len(updated)} field diperbarui: {', '.join(updated)}"
        }

    # ------------------------------------------------------------------
    # Pendidikan
    # ------------------------------------------------------------------
    def get_pendidikan(self) -> list:
        """Ambil daftar pendidikan."""
        return self.profile.get("pendidikan", [])

    def tambah_pendidikan(self, data: dict) -> dict:
        """Tambah data pendidikan.

        Args:
            data: dict dengan field: jenjang, institusi, jurusan, tahun_masuk,
                  tahun_lulus, ipk (opsional)

        Returns:
            dict: Status dengan ID pendidikan baru.
        """
        pendidikan = self.profile.setdefault("pendidikan", [])
        new_id = max([p.get("id", 0) for p in pendidikan], default=0) + 1
        data["id"] = new_id
        pendidikan.append(data)
        self._save_profile()

        return {
            "success": True,
            "id": new_id,
            "data": data,
            "message": f"✅ Pendidikan ditambahkan: {data.get('jenjang', '?')} {data.get('jurusan', '?')} di {data.get('institusi', '?')}"
        }

    def edit_pendidikan(self, edu_id: int, data: dict) -> dict:
        """Edit data pendidikan berdasarkan ID."""
        for p in self.profile.get("pendidikan", []):
            if p.get("id") == edu_id:
                p.update(data)
                self._save_profile()
                return {"success": True, "message": f"✅ Pendidikan ID {edu_id} diperbarui"}
        return {"success": False, "error": f"Pendidikan dengan ID {edu_id} tidak ditemukan"}

    def hapus_pendidikan(self, edu_id: int) -> dict:
        """Hapus data pendidikan berdasarkan ID."""
        pendidikan = self.profile.get("pendidikan", [])
        for i, p in enumerate(pendidikan):
            if p.get("id") == edu_id:
                removed = pendidikan.pop(i)
                self._save_profile()
                return {"success": True, "removed": removed, "message": f"✅ Pendidikan ID {edu_id} dihapus"}
        return {"success": False, "error": f"Pendidikan dengan ID {edu_id} tidak ditemukan"}

    # ------------------------------------------------------------------
    # Pengalaman Kerja
    # ------------------------------------------------------------------
    def get_pengalaman(self) -> list:
        """Ambil daftar pengalaman kerja."""
        return self.profile.get("pengalaman", [])

    def tambah_pengalaman(self, data: dict) -> dict:
        """Tambah data pengalaman kerja."""
        pengalaman = self.profile.setdefault("pengalaman", [])
        new_id = max([p.get("id", 0) for p in pengalaman], default=0) + 1
        data["id"] = new_id
        pengalaman.append(data)
        self._save_profile()

        return {
            "success": True,
            "id": new_id,
            "data": data,
            "message": f"✅ Pengalaman ditambahkan: {data.get('posisi', '?')} di {data.get('perusahaan', '?')}"
        }

    def edit_pengalaman(self, exp_id: int, data: dict) -> dict:
        """Edit pengalaman kerja berdasarkan ID."""
        for p in self.profile.get("pengalaman", []):
            if p.get("id") == exp_id:
                p.update(data)
                self._save_profile()
                return {"success": True, "message": f"✅ Pengalaman ID {exp_id} diperbarui"}
        return {"success": False, "error": f"Pengalaman dengan ID {exp_id} tidak ditemukan"}

    def hapus_pengalaman(self, exp_id: int) -> dict:
        """Hapus pengalaman kerja berdasarkan ID."""
        pengalaman = self.profile.get("pengalaman", [])
        for i, p in enumerate(pengalaman):
            if p.get("id") == exp_id:
                removed = pengalaman.pop(i)
                self._save_profile()
                return {"success": True, "removed": removed, "message": f"✅ Pengalaman ID {exp_id} dihapus"}
        return {"success": False, "error": f"Pengalaman dengan ID {exp_id} tidak ditemukan"}

    # ------------------------------------------------------------------
    # Keahlian
    # ------------------------------------------------------------------
    def get_keahlian(self) -> list:
        """Ambil daftar keahlian."""
        return self.profile.get("keahlian", [])

    def tambah_keahlian(self, skill: str) -> dict:
        """Tambah keahlian."""
        keahlian = self.profile.setdefault("keahlian", [])
        if skill in keahlian:
            return {"success": False, "error": f"Keahlian '{skill}' sudah ada"}
        keahlian.append(skill)
        self._save_profile()
        return {"success": True, "message": f"✅ Keahlian '{skill}' ditambahkan"}

    def hapus_keahlian(self, skill: str) -> dict:
        """Hapus keahlian."""
        keahlian = self.profile.get("keahlian", [])
        if skill in keahlian:
            keahlian.remove(skill)
            self._save_profile()
            return {"success": True, "message": f"✅ Keahlian '{skill}' dihapus"}
        return {"success": False, "error": f"Keahlian '{skill}' tidak ditemukan"}

    # ------------------------------------------------------------------
    # Sertifikat
    # ------------------------------------------------------------------
    def get_sertifikat(self) -> list:
        """Ambil daftar sertifikat."""
        return self.profile.get("sertifikat", [])

    def tambah_sertifikat(self, data: dict) -> dict:
        """Tambah sertifikat."""
        sertifikat = self.profile.setdefault("sertifikat", [])
        new_id = max([s.get("id", 0) for s in sertifikat], default=0) + 1
        data["id"] = new_id
        sertifikat.append(data)
        self._save_profile()
        return {
            "success": True,
            "id": new_id,
            "message": f"✅ Sertifikat ditambahkan: {data.get('nama', '?')}"
        }

    def hapus_sertifikat(self, cert_id: int) -> dict:
        """Hapus sertifikat berdasarkan ID."""
        sertifikat = self.profile.get("sertifikat", [])
        for i, s in enumerate(sertifikat):
            if s.get("id") == cert_id:
                removed = sertifikat.pop(i)
                self._save_profile()
                return {"success": True, "removed": removed, "message": f"✅ Sertifikat ID {cert_id} dihapus"}
        return {"success": False, "error": f"Sertifikat dengan ID {cert_id} tidak ditemukan"}

    # ------------------------------------------------------------------
    # Dokumen
    # ------------------------------------------------------------------
    def get_dokumen(self) -> dict:
        """Ambil daftar dokumen."""
        return self.profile.get("dokumen", {})

    def tambah_dokumen(self, nama: str, file_path: str) -> dict:
        """Tambah/simpan dokumen ke data folder user.

        Args:
            nama: Nama dokumen (ijazah, cv, transkrip, ktp, dll)
            file_path: Path ke file asli

        Returns:
            dict: Status dengan path file yang disalin.
        """
        if not self.is_setup():
            return {"success": False, "error": "Data folder belum di-setup. Jalankan /data-user setup dulu"}

        file_path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.exists(file_path):
            return {"success": False, "error": f"File tidak ditemukan: {file_path}"}

        data_folder = self.profile["data_folder"]
        ext = os.path.splitext(file_path)[1]
        dest_name = f"{nama}{ext}"

        # Tentukan subfolder berdasarkan nama
        if nama in ("foto",):
            subfolder = "foto"
        elif nama in ("ijazah",):
            subfolder = "ijazah"
        elif nama in ("cv",):
            subfolder = "cv"
        elif nama in ("sertifikat_kompetensi",):
            subfolder = "sertifikat"
        else:
            subfolder = "dokumen"

        dest_dir = os.path.join(data_folder, subfolder)
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, dest_name)

        try:
            shutil.copy2(file_path, dest_path)
        except OSError as e:
            return {"success": False, "error": f"Gagal menyalin file: {e}"}

        # Simpan referensi relatif
        rel_path = os.path.relpath(dest_path, data_folder)
        dokumen = self.profile.setdefault("dokumen", {})
        dokumen[nama] = rel_path
        self._save_profile()

        label = DOKUMEN_LABELS.get(nama, nama)
        return {
            "success": True,
            "path": dest_path,
            "message": f"✅ Dokumen '{label}' berhasil disimpan ke:\n   {dest_path}"
        }

    def get_dokumen_path(self, nama: str) -> str:
        """Ambil full path dokumen berdasarkan nama."""
        if not self.is_setup():
            return None
        dokumen = self.profile.get("dokumen", {})
        rel_path = dokumen.get(nama)
        if not rel_path:
            return None
        full_path = os.path.join(self.profile["data_folder"], rel_path)
        return full_path if os.path.exists(full_path) else None

    # ------------------------------------------------------------------
    # Ringkasan
    # ------------------------------------------------------------------
    def get_ringkasan(self) -> str:
        """Ambil ringkasan data user dalam format teks."""
        profil = self.get_profil()
        lines = ["═══ PROFIL USER ═══\n"]

        # Data diri
        lines.append("📋 Data Diri:")
        for field, label in FIELD_LABELS.items():
            val = profil.get(field, "-")
            if val:
                lines.append(f"   {label}: {val}")

        # Pendidikan
        pendidikan = self.get_pendidikan()
        if pendidikan:
            lines.append(f"\n🎓 Pendidikan ({len(pendidikan)}):")
            for p in pendidikan:
                lines.append(f"   {p.get('jenjang', '?')} - {p.get('jurusan', '?')} di {p.get('institusi', '?')} ({p.get('tahun_masuk', '?')}-{p.get('tahun_lulus', '?')})")

        # Pengalaman
        pengalaman = self.get_pengalaman()
        if pengalaman:
            lines.append(f"\n💼 Pengalaman Kerja ({len(pengalaman)}):")
            for p in pengalaman:
                lines.append(f"   {p.get('posisi', '?')} di {p.get('perusahaan', '?')} ({p.get('tahun_masuk', '?')}-{p.get('tahun_keluar', 'sekarang')})")

        # Keahlian
        keahlian = self.get_keahlian()
        if keahlian:
            lines.append(f"\n🛠️ Keahlian: {', '.join(keahlian)}")

        # Sertifikat
        sertifikat = self.get_sertifikat()
        if sertifikat:
            lines.append(f"\n📜 Sertifikat ({len(sertifikat)}):")
            for s in sertifikat:
                lines.append(f"   {s.get('nama', '?')} - {s.get('penerbit', '?')} ({s.get('tahun', '?')})")

        # Dokumen
        dokumen = self.get_dokumen()
        if dokumen:
            lines.append(f"\n📎 Dokumen ({len(dokumen)}):")
            for nama, path in dokumen.items():
                label = DOKUMEN_LABELS.get(nama, nama)
                exists = os.path.exists(os.path.join(self.profile.get("data_folder", ""), path))
                status = "✅" if exists else "❌"
                lines.append(f"   {status} {label}: {path}")

        return "\n".join(lines)

    def get_data_for_letter(self) -> str:
        """Ambil data user dalam format yang cocok untuk surat lamaran."""
        profil = self.get_profil()
        lines = []

        lines.append(f"Nama: {profil.get('nama_lengkap', '-')}")
        lines.append(f"Tempat/Tanggal Lahir: {profil.get('tempat_lahir', '-')}, {profil.get('tanggal_lahir', '-')}")
        lines.append(f"Jenis Kelamin: {profil.get('jenis_kelamin', '-')}")
        lines.append(f"Alamat: {profil.get('alamat', '-')}")
        lines.append(f"No. HP: {profil.get('no_hp', '-')}")
        lines.append(f"Email: {profil.get('email', '-')}")
        lines.append(f"Kewarganegaraan: {profil.get('kewarganegaraan', 'Indonesia')}")

        # Pendidikan terakhir
        pendidikan = self.get_pendidikan()
        if pendidikan:
            latest = max(pendidikan, key=lambda p: int(p.get("tahun_lulus", "0") or "0"))
            lines.append(f"\nPendidikan Terakhir:")
            lines.append(f"  {latest.get('jenjang', '?')} {latest.get('jurusan', '?')}")
            lines.append(f"  {latest.get('institusi', '?')} ({latest.get('tahun_masuk', '?')}-{latest.get('tahun_lulus', '?')})")
            if latest.get("ipk"):
                lines.append(f"  IPK: {latest['ipk']}")

        # Pengalaman
        pengalaman = self.get_pengalaman()
        if pengalaman:
            lines.append(f"\nPengalaman Kerja:")
            for p in sorted(pengalaman, key=lambda x: x.get("tahun_masuk", ""), reverse=True):
                lines.append(f"  - {p.get('posisi', '?')} di {p.get('perusahaan', '?')} ({p.get('tahun_masuk', '?')}-{p.get('tahun_keluar', 'sekarang')})")
                if p.get("deskripsi"):
                    lines.append(f"    {p['deskripsi']}")

        # Keahlian
        keahlian = self.get_keahlian()
        if keahlian:
            lines.append(f"\nKeahlian: {', '.join(keahlian)}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _load_profile(self) -> dict:
        """Load profile dari file."""
        if os.path.exists(PROFILE_FILE):
            try:
                with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {"setup": False, "profil": {}, "pendidikan": [], "pengalaman": [], "keahlian": [], "sertifikat": [], "dokumen": {}}

    def _save_profile(self):
        """Simpan profile ke file."""
        self.profile["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.profile, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_mgr_instance = None


def get_user_data_manager(data_folder=None) -> UserDataManager:
    """Dapatkan singleton UserDataManager."""
    global _mgr_instance
    if _mgr_instance is None:
        _mgr_instance = UserDataManager(data_folder)
    return _mgr_instance


def reset_user_data_manager():
    """Reset singleton (untuk testing)."""
    global _mgr_instance
    _mgr_instance = None
