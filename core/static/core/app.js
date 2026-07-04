(function () {
    const body = document.body;
    const readingToggle = document.getElementById("readingToggle");
    const readingMode = localStorage.getItem("peckish-reading-mode") === "true";

    function setReadingMode(enabled) {
        body.classList.toggle("accessible-reading", enabled);
        if (readingToggle) {
            readingToggle.setAttribute("aria-pressed", enabled ? "true" : "false");
        }
        localStorage.setItem("peckish-reading-mode", enabled ? "true" : "false");
    }

    setReadingMode(readingMode);

    if (readingToggle) {
        readingToggle.addEventListener("click", function () {
            setReadingMode(!body.classList.contains("accessible-reading"));
        });
    }

    const levelToast = document.querySelector("[data-level-toast]");
    if (levelToast) {
        window.setTimeout(function () {
            levelToast.classList.add("is-hiding");
            window.setTimeout(function () {
                levelToast.remove();
            }, 320);
        }, 4200);
    }

    document.querySelectorAll("[data-flashcard]").forEach(function (card) {
        function flipCard() {
            const flipped = !card.classList.contains("is-flipped");
            card.classList.toggle("is-flipped", flipped);
            card.setAttribute("aria-pressed", flipped ? "true" : "false");
        }

        card.addEventListener("click", flipCard);
        card.addEventListener("keydown", function (event) {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                flipCard();
            }
        });
    });

    function drawMindmapConnectors(canvas) {
        const svg = canvas.querySelector("[data-mindmap-connectors]");
        const center = canvas.querySelector("[data-mindmap-center]");
        const nodes = Array.from(canvas.querySelectorAll("[data-mindmap-node]"));
        if (!svg || !center || !nodes.length) {
            return;
        }

        const canvasRect = canvas.getBoundingClientRect();
        svg.setAttribute("viewBox", "0 0 " + canvasRect.width + " " + canvasRect.height);
        svg.replaceChildren();

        function rectFor(element) {
            const rect = element.getBoundingClientRect();
            return {
                left: rect.left - canvasRect.left,
                top: rect.top - canvasRect.top,
                width: rect.width,
                height: rect.height,
                centerX: rect.left - canvasRect.left + rect.width / 2,
                centerY: rect.top - canvasRect.top + rect.height / 2
            };
        }

        function edgePoint(rect, targetX, targetY) {
            const dx = targetX - rect.centerX;
            const dy = targetY - rect.centerY;
            if (Math.abs(dx) < 0.1 && Math.abs(dy) < 0.1) {
                return { x: rect.centerX, y: rect.centerY };
            }
            const scaleX = dx ? (rect.width / 2) / Math.abs(dx) : Infinity;
            const scaleY = dy ? (rect.height / 2) / Math.abs(dy) : Infinity;
            const scale = Math.min(scaleX, scaleY);
            return {
                x: rect.centerX + dx * scale,
                y: rect.centerY + dy * scale
            };
        }

        function svgElement(name, attributes) {
            const element = document.createElementNS("http://www.w3.org/2000/svg", name);
            Object.entries(attributes).forEach(function ([key, value]) {
                element.setAttribute(key, value);
            });
            return element;
        }

        const centerRect = rectFor(center);
        nodes.forEach(function (node) {
            const nodeRect = rectFor(node);
            const start = edgePoint(centerRect, nodeRect.centerX, nodeRect.centerY);
            const end = edgePoint(nodeRect, centerRect.centerX, centerRect.centerY);

            svg.appendChild(svgElement("line", {
                x1: start.x.toFixed(1),
                y1: start.y.toFixed(1),
                x2: end.x.toFixed(1),
                y2: end.y.toFixed(1),
                stroke: "#111111",
                "stroke-width": "3",
                "stroke-linecap": "round"
            }));
            svg.appendChild(svgElement("circle", {
                cx: start.x.toFixed(1),
                cy: start.y.toFixed(1),
                r: "4",
                fill: "#fffdf9",
                stroke: "#111111",
                "stroke-width": "3"
            }));
            svg.appendChild(svgElement("circle", {
                cx: end.x.toFixed(1),
                cy: end.y.toFixed(1),
                r: "4",
                fill: "#fffdf9",
                stroke: "#111111",
                "stroke-width": "3"
            }));
        });
    }

    document.querySelectorAll("[data-mindmap-canvas]").forEach(function (canvas) {
        let frame = null;
        function scheduleDraw() {
            if (frame) {
                window.cancelAnimationFrame(frame);
            }
            frame = window.requestAnimationFrame(function () {
                frame = null;
                drawMindmapConnectors(canvas);
            });
        }

        scheduleDraw();
        window.addEventListener("resize", scheduleDraw);
        if ("ResizeObserver" in window) {
            const observer = new ResizeObserver(scheduleDraw);
            observer.observe(canvas);
            canvas.querySelectorAll("[data-mindmap-center], [data-mindmap-node]").forEach(function (element) {
                observer.observe(element);
            });
        }
        if (document.fonts && document.fonts.ready) {
            document.fonts.ready.then(scheduleDraw).catch(function () {});
        }
    });

    const sourceForm = document.querySelector("[data-source-form]");
    if (sourceForm) {
        const radios = sourceForm.querySelectorAll("input[name='source_type']");
        const panels = sourceForm.querySelectorAll("[data-source-panel]");

        function syncPanels() {
            const selected = sourceForm.querySelector("input[name='source_type']:checked").value;
            panels.forEach(function (panel) {
                panel.classList.toggle("hidden", panel.dataset.sourcePanel !== selected);
            });
        }

        radios.forEach(function (radio) {
            radio.addEventListener("change", syncPanels);
        });
        syncPanels();
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const transcribeUrl = body.dataset.transcribeUrl;

    function getCsrfToken() {
        const field = document.querySelector("input[name='csrfmiddlewaretoken']");
        if (field) {
            return field.value;
        }
        const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    function setMicLabel(button, label) {
        button.innerHTML = '<span class="mic-dot" aria-hidden="true"></span> ' + label;
    }

    function setVoiceStatus(button, message) {
        const form = button.closest("form");
        const status = form ? form.querySelector("[data-voice-status]") : null;
        if (status) {
            status.textContent = message || "";
        }
    }

    function normaliseText(text) {
        return text.replace(/\s+/g, " ").trim();
    }

    function writeTranscript(target, baseText, transcript) {
        target.value = normaliseText([baseText, transcript].filter(Boolean).join(" "));
        target.dispatchEvent(new Event("input", { bubbles: true }));
    }

    function appendTranscript(target, transcript) {
        target.value = normaliseText([target.value, transcript].filter(Boolean).join(" "));
        target.dispatchEvent(new Event("input", { bubbles: true }));
        target.focus();
    }

    function supportsRecording() {
        return Boolean(
            navigator.mediaDevices &&
            navigator.mediaDevices.getUserMedia &&
            window.MediaRecorder &&
            transcribeUrl
        );
    }

    function chooseMimeType() {
        const options = [
            "audio/webm;codecs=opus",
            "audio/webm",
            "audio/mp4",
            "audio/wav"
        ];
        return options.find(function (type) {
            return window.MediaRecorder && MediaRecorder.isTypeSupported(type);
        }) || "";
    }

    async function uploadRecording(blob, mimeType, target, button) {
        const formData = new FormData();
        formData.append("audio", blob, "peckish-explanation.webm");
        formData.append("mime_type", mimeType || blob.type || "audio/webm");

        button.disabled = true;
        button.classList.add("is-working");
        setMicLabel(button, "Transcribing");
        setVoiceStatus(button, "Transcribing your recording...");

        try {
            const response = await fetch(transcribeUrl, {
                method: "POST",
                headers: {
                    "X-CSRFToken": getCsrfToken()
                },
                body: formData
            });
            const data = await response.json().catch(function () {
                return {};
            });
            if (!response.ok || !data.ok) {
                throw new Error(data.error || "Peckish could not transcribe that recording.");
            }
            appendTranscript(target, data.transcript);
            setVoiceStatus(button, "Transcript added. You can edit it before sending.");
        } catch (error) {
            setVoiceStatus(button, error.message || "Transcription failed. Typing still works.");
        } finally {
            button.disabled = false;
            button.classList.remove("is-working");
            setMicLabel(button, "Speak");
        }
    }

    document.querySelectorAll("[data-speech-button]").forEach(function (button) {
        const target = document.getElementById(button.dataset.speechTarget);
        if (!target) {
            button.disabled = true;
            return;
        }

        let mode = SpeechRecognition ? "live" : "record";
        let recognition = null;
        let isListening = false;
        let baseText = "";
        let committedTranscript = "";

        let recorder = null;
        let mediaStream = null;
        let chunks = [];
        let recordingMimeType = "";

        function resetButton() {
            button.classList.remove("is-recording");
            setMicLabel(button, "Speak");
        }

        function stopTracks() {
            if (mediaStream) {
                mediaStream.getTracks().forEach(function (track) {
                    track.stop();
                });
                mediaStream = null;
            }
        }

        async function startRecordingFallback() {
            if (!supportsRecording()) {
                button.disabled = true;
                setVoiceStatus(button, "Voice input is unavailable here. Please type your answer.");
                return;
            }

            try {
                mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                recordingMimeType = chooseMimeType();
                chunks = [];
                recorder = new MediaRecorder(
                    mediaStream,
                    recordingMimeType ? { mimeType: recordingMimeType } : undefined
                );

                recorder.addEventListener("dataavailable", function (event) {
                    if (event.data && event.data.size > 0) {
                        chunks.push(event.data);
                    }
                });

                recorder.addEventListener("stop", function () {
                    const blob = new Blob(chunks, { type: recordingMimeType || "audio/webm" });
                    stopTracks();
                    if (!blob.size) {
                        resetButton();
                        setVoiceStatus(button, "No audio was captured. Try again or type instead.");
                        return;
                    }
                    uploadRecording(blob, recordingMimeType, target, button);
                });

                recorder.start();
                button.classList.add("is-recording");
                setMicLabel(button, "Stop");
                setVoiceStatus(button, "Recording... press Stop when you are finished.");
            } catch (error) {
                stopTracks();
                resetButton();
                setVoiceStatus(button, "Microphone access was blocked. Typing still works.");
            }
        }

        function stopRecordingFallback() {
            if (recorder && recorder.state !== "inactive") {
                setVoiceStatus(button, "Preparing audio...");
                recorder.stop();
            }
        }

        if (SpeechRecognition) {
            recognition = new SpeechRecognition();
            recognition.lang = navigator.language || "en-GB";
            recognition.interimResults = true;
            recognition.continuous = true;

            recognition.addEventListener("start", function () {
                isListening = true;
                baseText = target.value.trim();
                committedTranscript = "";
                button.classList.add("is-recording");
                setMicLabel(button, "Stop");
                setVoiceStatus(button, "Listening live...");
            });

            recognition.addEventListener("result", function (event) {
                let interimTranscript = "";
                for (let index = event.resultIndex; index < event.results.length; index += 1) {
                    const transcript = event.results[index][0].transcript;
                    if (event.results[index].isFinal) {
                        committedTranscript = normaliseText(committedTranscript + " " + transcript);
                    } else {
                        interimTranscript += transcript;
                    }
                }
                writeTranscript(target, baseText, normaliseText(committedTranscript + " " + interimTranscript));
            });

            recognition.addEventListener("error", function (event) {
                isListening = false;
                resetButton();
                if (supportsRecording()) {
                    mode = "record";
                    setVoiceStatus(
                        button,
                        "Live transcription is not available in this browser. Press Speak again to record instead."
                    );
                } else {
                    setVoiceStatus(button, "Live transcription is unavailable here. Typing still works.");
                }
                if (event.error === "not-allowed") {
                    setVoiceStatus(button, "Microphone access was blocked. Allow the mic or type instead.");
                }
            });

            recognition.addEventListener("end", function () {
                const heardSpeech = committedTranscript.trim() || target.value.trim() !== baseText;
                isListening = false;
                resetButton();
                setVoiceStatus(
                    button,
                    heardSpeech ? "Transcript added. You can edit it before sending." : "No speech was heard. Try again or type instead."
                );
                target.focus();
            });
        }

        if (!SpeechRecognition && !supportsRecording()) {
            button.disabled = true;
            setVoiceStatus(button, "Voice input is unavailable here. Please type your answer.");
            return;
        }

        if (!SpeechRecognition && supportsRecording()) {
            setVoiceStatus(button, "Press Speak to record. The transcript appears after you press Stop.");
        }

        button.addEventListener("click", function () {
            if (mode === "record") {
                if (recorder && recorder.state === "recording") {
                    stopRecordingFallback();
                } else {
                    startRecordingFallback();
                }
                return;
            }

            if (isListening) {
                recognition.stop();
                return;
            }

            try {
                recognition.start();
            } catch (error) {
                if (supportsRecording()) {
                    mode = "record";
                    setVoiceStatus(button, "Live transcription could not start. Press Speak again to record instead.");
                } else {
                    setVoiceStatus(button, "Live transcription could not start. Typing still works.");
                }
                resetButton();
            }
        });
    });

    document.querySelectorAll("[data-speak-button]").forEach(function (button) {
        const speechNode = document.querySelector("[data-peckish-speech]");
        if (!("speechSynthesis" in window) || !speechNode) {
            button.disabled = true;
            return;
        }
        button.addEventListener("click", function () {
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(speechNode.textContent.trim());
            utterance.rate = 0.96;
            utterance.pitch = 1.12;
            window.speechSynthesis.speak(utterance);
        });
    });
})();
