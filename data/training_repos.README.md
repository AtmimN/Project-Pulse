# Daftar Repositori Latih (diisi pemilik repositori)

Isi array `repos` di `training_repos.json` dengan **30–60 repositori** yang memenuhi `criteria`.

Format tiap entri:

```json
{"full_name": "pemilik/nama-repo", "release_tag": null}
```

- `release_tag` boleh `null` (aplikasi mencari rilis stabil pertama) atau diisi manual (misalnya `"v1.0.0"`) bila tag semver tidak jelas.
- Jangan memasukkan repositori dari `monitor_repos.json`.
- Tulis alasan pemilihan di laporan; kriteria di atas ikut ditampilkan di aplikasi.
- AI pembangun **tidak boleh** mengisi atau mengarang daftar ini.
