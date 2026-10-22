(() => {
    "use strict";
    const dateFormat = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });
    document.querySelectorAll("time[data-timestamp]").forEach((element) => {
        const date = new Date(Number(element.dataset.timestamp) * 1000);
        if (Number.isNaN(date.getTime())) return;
        element.dateTime = date.toISOString();
        element.textContent = dateFormat.format(date);
    });
})();
