async function loadDeviceInfo() {
    try {
        const res = await fetch("http://localhost:8000/info");

        if (!res.ok) {
            throw new Error("Failed to load device information.");
        }

        const data = await res.json();

        document.getElementById("sendUsername").textContent =
            data.username || "Unknown";

        document.getElementById("sendUserIP").textContent =
            data.ip || "Unknown";

        document.getElementById("receiveUsername").textContent =
            data.username || "Unknown";

        document.getElementById("receiveUserIP").textContent =
            data.ip || "Unknown";
    } catch (error) {
        console.error("Info error:", error);
    }
}

loadDeviceInfo();

const tabs = document.querySelectorAll(".tab");
const panels = document.querySelectorAll(".panel");

const sendInstructions =
    document.getElementById("sendInstructions");

const receiveInstructions =
    document.getElementById("receiveInstructions");

const helpTitle =
    document.getElementById("helpTitle");

tabs.forEach(tab => {
    tab.addEventListener("click", event => {
        event.preventDefault();

        if (
            document
                .getElementById("sendButton")
                .classList.contains("transfer-active")
        ) {
            return;
        }

        const target = tab.dataset.tab;

        tabs.forEach(item => {
            item.classList.remove("active");
        });

        tab.classList.add("active");

        panels.forEach(panel => {
            panel.classList.remove("active");
        });

        const targetPanel =
            document.getElementById(target);

        if (targetPanel) {
            targetPanel.classList.add("active");
        }

        sendInstructions.classList.remove("active");
        receiveInstructions.classList.remove("active");

        if (target === "send") {
            sendInstructions.classList.add("active");
            helpTitle.textContent = "How to send";
        } else {
            receiveInstructions.classList.add("active");
            helpTitle.textContent = "How to receive";
        }
    });
});

const fileOption =
    document.getElementById("fileOption");

const folderOption =
    document.getElementById("folderOption");

const sendType =
    document.getElementById("sendType");

let transferType = "file";

fileOption.addEventListener("click", event => {
    event.preventDefault();

    transferType = "file";

    fileOption.classList.add("active");
    folderOption.classList.remove("active");

    sendType.textContent = "File";
});

folderOption.addEventListener("click", event => {
    event.preventDefault();

    transferType = "folder";

    folderOption.classList.add("active");
    fileOption.classList.remove("active");

    sendType.textContent = "Folder";
});

function createProgressUI(container) {
    let progress =
        container.querySelector(".transfer-progress");

    if (progress) {
        return progress;
    }

    progress = document.createElement("div");
    progress.className = "transfer-progress";

    progress.innerHTML = `
        <div class="progress-header">
            <span class="progress-status">Preparing transfer...</span>
            <span class="progress-percent">0%</span>
        </div>

        <div class="progress-track">
            <div class="progress-bar"></div>
        </div>

        <div class="progress-details">
            <span class="progress-size">0 B / 0 B</span>
            <span class="progress-speed">0 MB/s</span>
            <span class="progress-eta">Calculating...</span>
        </div>

        <div class="progress-file">
            <span>Current:</span>
            <strong>Preparing...</strong>
        </div>
    `;

    container.appendChild(progress);

    return progress;
}

function formatBytes(bytes) {
    if (!bytes || bytes <= 0) {
        return "0 B";
    }

    const units = ["B", "KB", "MB", "GB", "TB"];

    const index =
        Math.floor(
            Math.log(bytes) / Math.log(1024)
        );

    const value =
        bytes / Math.pow(1024, index);

    return (
        value.toFixed(index === 0 ? 0 : 2) +
        " " +
        units[index]
    );
}

function formatSpeed(bytesPerSecond) {
    if (!bytesPerSecond || bytesPerSecond <= 0) {
        return "0 MB/s";
    }

    return (
        (bytesPerSecond / 1024 / 1024).toFixed(2) +
        " MB/s"
    );
}

function formatETA(seconds) {
    if (
        seconds === null ||
        seconds === undefined ||
        !isFinite(seconds) ||
        seconds < 0
    ) {
        return "Calculating...";
    }

    seconds = Math.round(seconds);

    if (seconds < 60) {
        return `${seconds}s remaining`;
    }

    const minutes = Math.floor(seconds / 60);
    const remaining = seconds % 60;

    if (minutes < 60) {
        return `${minutes}m ${remaining}s remaining`;
    }

    const hours = Math.floor(minutes / 60);

    return `${hours}h ${minutes % 60}m remaining`;
}

function updateProgress(container, data) {
    const progress =
        createProgressUI(container);

    const bar =
        progress.querySelector(".progress-bar");

    const percent =
        progress.querySelector(".progress-percent");

    const status =
        progress.querySelector(".progress-status");

    const size =
        progress.querySelector(".progress-size");

    const speed =
        progress.querySelector(".progress-speed");

    const eta =
        progress.querySelector(".progress-eta");

    const current =
        progress.querySelector(".progress-file strong");

    const percentage =
        Math.max(
            0,
            Math.min(
                100,
                Number(data.percent || 0)
            )
        );

    bar.style.width =
        percentage + "%";

    percent.textContent =
        percentage.toFixed(0) + "%";

    status.textContent =
        data.status_text ||
        "Transferring...";

    size.textContent =
        `${formatBytes(data.transferred || 0)} / ${formatBytes(data.total || 0)}`;

    speed.textContent =
        formatSpeed(data.speed || 0);

    eta.textContent =
        formatETA(data.eta);

    current.textContent =
        data.current_file ||
        "Preparing...";
}

async function monitorTransfer(
    jobId,
    container,
    onComplete
) {
    let stopped = false;

    while (!stopped) {
        try {
            const res = await fetch(
                `http://localhost:8000/transfer/${jobId}`
            );

            if (!res.ok) {
                throw new Error(
                    "Unable to read transfer status."
                );
            }

            const data = await res.json();

            console.log(
                "Transfer status:",
                data
            );

            updateProgress(
                container,
                data
            );

            if (data.status === "completed") {
                stopped = true;

                onComplete(
                    null,
                    data
                );

                break;
            }

            if (data.status === "failed") {
                stopped = true;

                onComplete(
                    new Error(
                        data.message ||
                        "Transfer failed."
                    ),
                    data
                );

                break;
            }

            await new Promise(resolve =>
                setTimeout(resolve, 400)
            );
        } catch (error) {
            stopped = true;

            onComplete(
                error,
                null
            );
        }
    }
}

async function TransferData(event) {
    if (event) {
        event.preventDefault();
    }

    const ip =
        document
            .getElementById("receiverIP")
            .value
            .trim();

    const path =
        document
            .getElementById("sendPath")
            .value
            .trim();

    const button =
        document.getElementById("sendButton");

    const message =
        document.getElementById("sendMessage");

    const transferBox =
        document.querySelector(".transfer-type");

    const panel =
        document.getElementById("send");

    if (!ip || !path) {
        message.className =
            "message error show";

        message.textContent =
            "Enter destination IP and file/folder path.";

        return;
    }

    button.disabled = true;

    button.classList.add(
        "loading",
        "transfer-active"
    );

    button.classList.remove("success");

    button.textContent =
        "Preparing Transfer...";

    transferBox.classList.add(
        "transferring"
    );

    panel.classList.add(
        "transfer-running"
    );

    message.className =
        "message show";

    message.textContent =
        "Connecting to receiver...";

    createProgressUI(panel);

    try {
        const res =
            await fetch(
                "http://localhost:8000/send",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body: JSON.stringify({
                        file: transferType,
                        receiverIP: ip,
                        sendPath: path
                    })
                }
            );

        if (!res.ok) {
            throw new Error(
                `Server error: ${res.status}`
            );
        }

        const result =
            await res.json();

        console.log(
            "Send started:",
            result
        );

        if (
            result.status !== "success" ||
            !result.job_id
        ) {
            throw new Error(
                result.message ||
                "Failed to start transfer."
            );
        }

        message.className =
            "message show";

        message.textContent =
            "Transfer started...";

        await new Promise(resolve => {
            monitorTransfer(
                result.job_id,
                panel,
                (error, data) => {
                    if (error) {
                        button.classList.remove(
                            "loading"
                        );

                        button.classList.add(
                            "error"
                        );

                        button.textContent =
                            "Transfer Failed";

                        transferBox.classList.remove(
                            "transferring"
                        );

                        message.className =
                            "message error show";

                        message.textContent =
                            "✕ " + error.message;

                        button.disabled = false;

                        resolve();

                        return;
                    }

                    button.classList.remove(
                        "loading"
                    );

                    button.classList.add(
                        "success"
                    );

                    button.textContent =
                        "✓ Transfer Complete";

                    transferBox.classList.remove(
                        "transferring"
                    );

                    message.className =
                        "message success show";

                    message.textContent =
                        transferType === "file"
                            ? "✓ File sent successfully."
                            : "✓ Folder sent successfully.";

                    button.disabled = false;

                    resolve();
                }
            );
        });
    } catch (error) {
        console.error(
            "Transfer error:",
            error
        );

        button.classList.remove(
            "loading",
            "transfer-active"
        );

        transferBox.classList.remove(
            "transferring"
        );

        button.textContent =
            "Transfer Failed";

        message.className =
            "message error show";

        message.textContent =
            "✕ " + error.message;

        button.disabled = false;
    } finally {
        panel.classList.remove(
            "transfer-running"
        );

        button.classList.remove(
            "transfer-active"
        );
    }
}

async function StartReceiver(event) {
    if (event) {
        event.preventDefault();
    }

    const destination =
        document
            .getElementById("receivePath")
            .value
            .trim();

    const receiveIP =
        document
            .getElementById("receiveUserIP")
            .textContent
            .trim();

    const senderIP =
        document
            .getElementById("receiveIP")
            .value
            .trim();

    const button =
        document.getElementById(
            "receiveButton"
        );

    const message =
        document.getElementById(
            "receiveMessage"
        );

    const userInfo =
        document.querySelector(
            "#receive .user-info"
        );

    const panel =
        document.getElementById(
            "receive"
        );

    if (!destination) {
        message.className =
            "message error show";

        message.textContent =
            "Enter destination folder.";

        return;
    }

    if (!senderIP) {
        message.className =
            "message error show";

        message.textContent =
            "Enter the sender IP address.";

        return;
    }

    button.disabled = true;

    button.classList.add(
        "loading"
    );

    button.textContent =
        "Connecting...";

    message.className =
        "message show";

    message.textContent =
        "Starting receiver...";

    createProgressUI(panel);

    try {
        const res =
            await fetch(
                "http://localhost:8000/receive",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body: JSON.stringify({
                        receiveIP: receiveIP,
                        senderIP: senderIP,
                        destination: destination
                    })
                }
            );

        if (!res.ok) {
            throw new Error(
                `Server error: ${res.status}`
            );
        }

        const result =
            await res.json();

        console.log(
            "Receive started:",
            result
        );

        if (
            result.status !== "success" ||
            !result.job_id
        ) {
            throw new Error(
                result.message ||
                "Failed to start receiver."
            );
        }

        button.classList.remove(
            "loading"
        );

        button.classList.add(
            "transfer-active"
        );

        button.textContent =
            "● Waiting for Sender";

        userInfo.classList.add(
            "listening"
        );

        message.className =
            "message success show";

        message.textContent =
            "✓ Receiver is ready. Waiting for incoming data...";

        monitorTransfer(
            result.job_id,
            panel,
            (error, data) => {
                if (error) {
                    button.classList.remove(
                        "transfer-active"
                    );

                    button.classList.remove(
                        "loading"
                    );

                    button.textContent =
                        "Connect & Receive";

                    button.disabled = false;

                    message.className =
                        "message error show";

                    message.textContent =
                        "✕ " + error.message;

                    return;
                }

                button.classList.remove(
                    "transfer-active"
                );

                button.classList.add(
                    "success"
                );

                button.textContent =
                    "✓ Receive Complete";

                message.className =
                    "message success show";

                message.textContent =
                    "✓ Transfer received successfully.";

                button.disabled = false;
            }
        );
    } catch (error) {
        console.error(
            "Receive error:",
            error
        );

        button.classList.remove(
            "loading"
        );

        button.textContent =
            "Connect & Receive";

        button.disabled = false;

        message.className =
            "message error show";

        message.textContent =
            "✕ " + error.message;
    }
}

document
    .getElementById("sendButton")
    .addEventListener(
        "click",
        TransferData
    );

document
    .getElementById("receiveButton")
    .addEventListener(
        "click",
        StartReceiver
    );

document
    .querySelectorAll("form")
    .forEach(form => {
        form.addEventListener(
            "submit",
            event => {
                event.preventDefault();
            }
        );
    });
