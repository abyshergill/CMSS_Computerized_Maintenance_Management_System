(() => {
  const cadence = document.getElementById("id_cadence");
  if (!cadence) return;

  const rows = {
    weekday: document.getElementById("id_weekday")?.closest("p"),
    dayOfMonth: document.getElementById("id_day_of_month")?.closest("p"),
    monthOfYear: document.getElementById("id_month_of_year")?.closest("p"),
  };

  const refresh = () => {
    const value = cadence.value;
    if (rows.weekday) rows.weekday.hidden = value !== "Weekly";
    if (rows.dayOfMonth) rows.dayOfMonth.hidden = !["Monthly", "Yearly"].includes(value);
    if (rows.monthOfYear) rows.monthOfYear.hidden = value !== "Yearly";
  };

  cadence.addEventListener("change", refresh);
  refresh();
})();
