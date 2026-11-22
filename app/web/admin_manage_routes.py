"""Modul rute kelola repositori, pemantauan, scraping manual, dan alert panel admin."""
from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, url_for

from app.db import connection, repos_repo, subscribers_repo
from app.services import admin_monitoring_service, admin_service
from app.web.admin_routes import admin_bp


@admin_bp.route("/repositori", methods=["GET"])
def repos():
    """Halaman kelola repositori pantau dan tampilan repositori latih."""
    db_target = current_app.config.get("DATABASE_PATH")
    data = admin_service.get_repos_admin_data(db_target)
    return render_template("admin/repositori.html", **data)


@admin_bp.route("/repositori/add", methods=["POST"])
def add_repo():
    """Menambahkan repositori pantau baru."""
    db_target = current_app.config.get("DATABASE_PATH")
    fn = request.form.get("full_name", "").strip()
    try:
        admin_service.add_monitor_repo_admin(fn, db_target)
        flash(f"Repositori pantau '{fn}' berhasil ditambahkan.", "success")
    except Exception as ex:
        flash(f"Gagal menambahkan repositori: {ex}", "danger")
    return redirect(url_for("admin.repos"))


@admin_bp.route("/repositori/toggle", methods=["POST"])
def toggle_repo():
    """Mengaktifkan atau menonaktifkan repositori pantau."""
    db_target = current_app.config.get("DATABASE_PATH")
    rid = int(request.form.get("repo_id", 0))
    act = int(request.form.get("active", 1))
    with connection.transaction(db_target) as conn:
        repos_repo.set_active(conn, rid, act)
    flash("Status repositori berhasil diperbarui.", "success")
    return redirect(url_for("admin.repos"))


@admin_bp.route("/pemantauan", methods=["GET"])
def pemantauan():
    """Halaman pemantauan pelanggan, riwayat alert, dan log penjadwal."""
    db_target = current_app.config.get("DATABASE_PATH")
    repo_f = request.args.get("repo", "").strip() or None
    type_f = request.args.get("type", "").strip() or None
    subs = admin_monitoring_service.get_subscribers_monitoring(db_target)
    alerts = admin_monitoring_service.get_alerts_history(repo_filter=repo_f, type_filter=type_f, db_path=db_target)
    jobs = admin_monitoring_service.get_scheduler_logs(db_path=db_target)
    return render_template("admin/pemantauan.html", subscribers=subs, alerts=alerts, jobs=jobs)


@admin_bp.route("/pemantauan/subscribers/toggle", methods=["POST"])
def toggle_subscriber():
    """Mengubah status aktif/nonaktif pelanggan bot."""
    db_target = current_app.config.get("DATABASE_PATH")
    token = request.form.get("token")
    if token:
        try:
            cid = admin_monitoring_service.decode_chat_id(token)
        except Exception:
            cid = 0
    else:
        cid = int(request.form.get("chat_id", 0))
    act = int(request.form.get("active", 1))
    with connection.transaction(db_target) as conn:
        subscribers_repo.set_active(conn, cid, act)
    flash(f"Status pelanggan {admin_monitoring_service.mask_chat_id(cid)} berhasil diubah.", "success")
    return redirect(url_for("admin.pemantauan"))


@admin_bp.route("/scrape", methods=["POST"])
def scrape_now():
    """Jalankan scraping manual sekarang."""
    db_target = current_app.config.get("DATABASE_PATH")
    try:
        res = admin_service.run_admin_scrape(db_target)
        flash(f"Scraping selesai: {res['new_comments']} komentar, {res['new_releases']} rilis baru.", "success")
    except Exception as ex:
        flash(f"Scraping tidak dapat dijalankan: {ex}", "danger")
    return redirect(request.referrer or url_for("admin.pemantauan"))


@admin_bp.route("/pengaturan-alert", methods=["GET"])
def pengaturan_alert():
    """Halaman pengaturan ambang batas alert dan kata kunci."""
    db_target = current_app.config.get("DATABASE_PATH")
    data = admin_monitoring_service.get_alert_settings_data(db_target)
    return render_template("admin/pengaturan_alert.html", **data)


@admin_bp.route("/pengaturan-alert/tiers", methods=["POST"])
def update_tiers():
    """Memperbarui nilai ambang batas alert."""
    db_target = current_app.config.get("DATABASE_PATH")
    for key, val in request.form.items():
        if key.startswith(("sentimen_turun_", "lonjakan_negatif_", "rilis_bermasalah_", "kata_kunci_")):
            try:
                admin_monitoring_service.update_alert_setting_val(key, float(val), db_target)
            except ValueError:
                pass
    flash("Nilai ambang alert berhasil disimpan.", "success")
    return redirect(url_for("admin.pengaturan_alert"))


@admin_bp.route("/pengaturan-alert/keywords/add", methods=["POST"])
def add_keyword():
    """Menambahkan kata kunci baru."""
    db_target = current_app.config.get("DATABASE_PATH")
    w = request.form.get("word", "")
    try:
        admin_monitoring_service.add_keyword_admin(w, db_target)
        flash(f"Kata kunci '{w.strip().lower()}' berhasil ditambahkan.", "success")
    except Exception as ex:
        flash(f"Gagal menambahkan kata kunci: {ex}", "danger")
    return redirect(url_for("admin.pengaturan_alert"))


@admin_bp.route("/pengaturan-alert/keywords/delete", methods=["POST"])
def delete_keyword():
    """Menghapus kata kunci."""
    db_target = current_app.config.get("DATABASE_PATH")
    kid = int(request.form.get("keyword_id", 0))
    admin_monitoring_service.delete_keyword_admin(kid, db_target)
    flash("Kata kunci berhasil dihapus.", "success")
    return redirect(url_for("admin.pengaturan_alert"))
