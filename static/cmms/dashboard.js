(() => {
  const healthPayload = document.getElementById("health-chart-data");
  const workOrderPayload = document.getElementById("work-order-chart-data");
  const healthCanvas = document.getElementById("health-chart");
  const workOrderCanvas = document.getElementById("work-order-chart");
  if (typeof Chart === "undefined" || !healthPayload || !workOrderPayload || !healthCanvas || !workOrderCanvas) return;

  const healthData = JSON.parse(healthPayload.textContent);
  const workOrderData = JSON.parse(workOrderPayload.textContent);
  const colors = ["#059669", "#d97706", "#e11d48"];
  const compact = window.matchMedia("(max-width: 640px)").matches;

  new Chart(healthCanvas, {
    type: "doughnut",
    data: { labels: healthData.labels, datasets: [{ data: healthData.values, backgroundColor: colors, borderWidth: 0 }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: compact ? "66%" : "70%",
      layout: { padding: compact ? 2 : 8 },
      plugins: { legend: { position: "bottom", labels: { boxWidth: compact ? 10 : 14, boxHeight: compact ? 10 : 14, padding: compact ? 12 : 20, font: { size: compact ? 10 : 12 } } } },
    },
  });

  new Chart(workOrderCanvas, {
    type: "bar",
    data: { labels: workOrderData.labels, datasets: [{ label: "Orders", data: workOrderData.values, backgroundColor: "#0f766e", borderRadius: 6 }] },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { right: compact ? 8 : 18, top: 4, bottom: 4 } },
      scales: {
        x: { beginAtZero: true, ticks: { precision: 0, font: { size: compact ? 9 : 11 }, maxTicksLimit: compact ? 5 : 8 }, grid: { color: "#e8eef4" } },
        y: { ticks: { autoSkip: false, font: { size: compact ? 9 : 11 } }, grid: { display: false } },
      },
      plugins: { legend: { display: false } },
    },
  });
})();
