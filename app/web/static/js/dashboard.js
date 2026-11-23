/**
 * Script visualisasi Chart.js untuk Dashboard ProjectPulse
 */
document.addEventListener("DOMContentLoaded", function () {
    initSentimentBarChart();
    initSentimentTrendChart();
    initModelBScatterChart();
});

function initSentimentBarChart() {
    const ctx = document.getElementById("chart-sentiment-bar");
    if (!ctx) return;

    fetch("/api/dashboard/sentiment-by-repo")
        .then(res => res.json())
        .then(data => {
            if (!data || data.length === 0 || data.every(d => d.total === 0)) {
                showEmptyChartMessage("container-sentiment-bar", "Belum ada data sentimen repositori pantau (30 hari).");
                return;
            }
            const labels = data.map(d => d.repo);
            const pos = data.map(d => d.pct_positive);
            const neu = data.map(d => d.pct_neutral);
            const neg = data.map(d => d.pct_negative);

            new Chart(ctx, {
                type: "bar",
                data: {
                    labels: labels,
                    datasets: [
                        { label: "% Positif", data: pos, backgroundColor: "#22c55e" },
                        { label: "% Netral", data: neu, backgroundColor: "#94a3b8" },
                        { label: "% Negatif", data: neg, backgroundColor: "#ef4444" }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { stacked: true },
                        y: { stacked: true, max: 100, title: { display: true, text: "Persentase (%)" } }
                    },
                    plugins: {
                        title: { display: true, text: "Komposisi Sentimen Komentar per Repositori (30 Hari)" }
                    }
                }
            });
        })
        .catch(() => showEmptyChartMessage("container-sentiment-bar", "Gagal memuat grafik komposisi sentimen."));
}

function initSentimentTrendChart() {
    const ctx = document.getElementById("chart-sentiment-trend");
    if (!ctx) return;

    fetch("/api/dashboard/sentiment-trend")
        .then(res => res.json())
        .then(data => {
            if (!data || data.length === 0) {
                showEmptyChartMessage("container-sentiment-trend", "Belum ada riwayat tren indeks sentimen bulanan.");
                return;
            }
            const colors = ["#2563eb", "#7c3aed", "#059669", "#d97706", "#dc2626", "#0891b2"];
            const allMonths = Array.from(new Set(data.flatMap(d => d.points.map(p => p.month)))).sort();
            if (allMonths.length === 0) {
                showEmptyChartMessage("container-sentiment-trend", "Belum ada riwayat tren indeks sentimen bulanan.");
                return;
            }

            const datasets = data.map((d, i) => {
                const monthMap = Object.fromEntries(d.points.map(p => [p.month, p.index]));
                return {
                    label: d.repo,
                    data: allMonths.map(m => monthMap[m] !== undefined ? monthMap[m] : null),
                    borderColor: colors[i % colors.length],
                    backgroundColor: colors[i % colors.length],
                    tension: 0.2,
                    spanGaps: true
                };
            });

            new Chart(ctx, {
                type: "line",
                data: { labels: allMonths, datasets: datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: { min: -1.0, max: 1.0, title: { display: true, text: "Indeks Sentimen (-1 s/d +1)" } },
                        x: { title: { display: true, text: "Bulan" } }
                    },
                    plugins: {
                        title: { display: true, text: "Tren Indeks Sentimen Bulanan per Repositori" }
                    }
                }
            });
        })
        .catch(() => showEmptyChartMessage("container-sentiment-trend", "Gagal memuat grafik tren bulanan."));
}

function initModelBScatterChart() {
    const ctx = document.getElementById("chart-model-b");
    if (!ctx) return;

    fetch("/api/dashboard/regression-b")
        .then(res => res.json())
        .then(resData => {
            if (!resData || resData.status === "not_trained") {
                showEmptyChartMessage("container-model-b", "Model B belum dilatih atau berkas model belum tersedia.");
                return;
            }
            if (!resData.pairs) {
                showEmptyChartMessage("container-model-b", "Metrik evaluasi tidak memuat data pasangan prediksi (pairs).");
                return;
            }
            if (resData.pairs.length === 0) {
                showEmptyChartMessage("container-model-b", "Jumlah sampel pasangan prediksi tidak mencukupi untuk ditampilkan.");
                return;
            }
            // Pasangan predictions aktual vs prediksi untuk scatter plot
            const predictions = resData.pairs;
            const points = predictions.map(p => ({ x: p.actual, y: p.predicted }));

            new Chart(ctx, {
                type: "scatter",
                data: {
                    datasets: [
                        {
                            label: "Proyek NASA93 (Aktual vs Prediksi)",
                            data: points,
                            backgroundColor: "#0f766e"
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { type: "logarithmic", title: { display: true, text: "Usaha Aktual (person-bulan, log scale)" } },
                        y: { type: "logarithmic", title: { display: true, text: "Usaha Prediksi (person-bulan, log scale)" } }
                    },
                    plugins: {
                        title: { display: true, text: "Scatter Model B: Aktual vs Prediksi Usaha NASA93" }
                    }
                }
            });
        })
        .catch(() => showEmptyChartMessage("container-model-b", "Gagal memuat grafik Model B."));
}

function showEmptyChartMessage(containerId, message) {
    const container = document.getElementById(containerId);
    if (container) {
        container.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;min-height:220px;color:var(--text-muted);font-size:0.9rem;text-align:center;padding:1.5rem;">${message}</div>`;
    }
}
