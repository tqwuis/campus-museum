const charts = {};
const buttons = document.querySelectorAll("[data-panel]");
const panels = document.querySelectorAll(".panel");
const status = document.querySelector("#status");

function showPanel(id) {
    for (const panel of panels) {
        panel.hidden = panel.id !== id;
    }
    for (const button of buttons) {
        button.setAttribute("aria-pressed", String(button.dataset.panel === id));
    }
    // 숨겨져 있던 canvas가 표시된 다음 새 너비에 맞춥니다.
    requestAnimationFrame(function () {
        if (charts[id]) charts[id].resize();
    });
}

for (const button of buttons) {
    button.addEventListener("click", function () {
        showPanel(button.dataset.panel);
    });
}

function readCsv(path) {
    return new Promise(function (resolve, reject) {
        Papa.parse(path, {
            download: true,
            header: false,
            skipEmptyLines: "greedy",
            complete: resolve,
            error: reject
        });
    });
}

function drawCharts(healthRows, managementRows) {
    const healthLabels = healthRows.map(function (row) { return row[1]; });
    const healthScores = healthRows.map(function (row) { return Number(row[3]); });
    const managementLabels = managementRows.map(function (row) { return row[2]; });
    const methods = [
        ["아침 식사", 4, "#7455e9"],
        ["적정 수면", 6, "#008678"],
        ["규칙적 운동", 8, "#c56200"]
    ];

    for (const chart of Object.values(charts)) chart.destroy();

    charts.visitors = new Chart(document.querySelector("#visitors-chart"), {
        type: "line",
        data: {
            labels: healthLabels,
            datasets: [{
                label: "건강 상태 점수",
                data: healthScores,
                borderColor: "#7455e9",
                backgroundColor: "rgba(116, 85, 233, 0.18)",
                pointBackgroundColor: "#7455e9",
                pointBorderColor: "#ffffff",
                pointBorderWidth: 2,
                pointRadius: 5,
                tension: 0.25,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { y: { beginAtZero: true, min: 4, max: 7, title: { display: true, text: "점수" } } },
            plugins: { tooltip: { mode: "index", intersect: false } }
        }
    });

    charts.satisfaction = new Chart(document.querySelector("#satisfaction-chart"), {
        type: "bar",
        data: {
            labels: managementLabels,
            datasets: methods.map(function (method) {
                return {
                    label: method[0] + " 실천율(%)",
                    data: managementRows.map(function (row) { return Number(row[method[1]]); }),
                    backgroundColor: method[2]
                };
            })
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { y: { beginAtZero: true, max: 100, title: { display: true, text: "%" } } }
        }
    });
}

if (typeof Papa === "undefined" || typeof Chart === "undefined") {
    status.textContent = "라이브러리를 불러오지 못했습니다. 네트워크를 확인하세요.";
} else {
    Promise.all([
        readCsv("./data/자신의_건강_상태.csv"),
        readCsv("./data/건강관리_13세_이상_인구.csv")
    ]).then(function (results) {
        const healthRows = results[0].data.filter(function (row) {
            return row[0] === "연령별" && row[1] && Number.isFinite(Number(row[3]));
        });
        const managementRows = results[1].data.filter(function (row) {
            return row[1] === "연령" && row[2] && Number.isFinite(Number(row[4]));
        });
        if (healthRows.length === 0 || managementRows.length === 0) {
            status.textContent = "그래프로 표시할 행이 없습니다.";
            return;
        }
        drawCharts(healthRows, managementRows);
        showPanel("visitors");
        status.textContent = healthRows.length + "개 연령대의 건강 통계를 표시했습니다.";
    }).catch(function () {
        status.textContent = "CSV 경로와 네트워크를 확인하세요.";
    });
}