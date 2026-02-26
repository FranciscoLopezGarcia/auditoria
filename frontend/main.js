document.addEventListener("DOMContentLoaded", () => {
    const fileInput = document.getElementById("files");
    const dropArea = document.getElementById("dropArea");
    const fileList = document.getElementById("fileList");
    const processBtn = document.getElementById("processBtn");
    const btnText = document.querySelector(".btn-text");
    const btnLoader = document.getElementById("btnLoader");
    const statusAlert = document.getElementById("statusAlert");
    const excelUpload = document.getElementById("excelUpload");
    const excelFile = document.getElementById("excelFile");
    const modeRadios = document.querySelectorAll('input[name="mode"]');

    let selectedFiles = [];

    // --- Mode Selector ---
    modeRadios.forEach(radio => {
        radio.addEventListener("change", (e) => {
            excelUpload.style.display = e.target.value === "update" ? "block" : "none";
            if (e.target.value === "new") {
                excelFile.value = "";
            }
        });
    });

    // --- Drag and Drop Events ---
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => dropArea.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => dropArea.classList.remove('dragover'), false);
    });

    dropArea.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        handleFiles(dt.files);
    });

    fileInput.addEventListener("change", (e) => {
        handleFiles(e.target.files);
        // Reset input so selecting the same file again works
        fileInput.value = "";
    });

    function handleFiles(files) {
        Array.from(files).forEach(file => {
            if (file.type === "application/pdf" && !selectedFiles.some(f => f.name === file.name)) {
                selectedFiles.push(file);
            }
        });
        updateFileList();
    }

    function removeFile(index) {
        selectedFiles.splice(index, 1);
        updateFileList();
    }

    // Attach function to window so it can be called from inline HTML
    window.removeFile = removeFile;

    function updateFileList() {
        fileList.innerHTML = "";
        selectedFiles.forEach((file, index) => {
            const item = document.createElement("div");
            item.className = "file-item";
            item.innerHTML = `
                <span class="file-name" title="${file.name}">${file.name}</span>
                <button class="file-remove" onclick="removeFile(${index})" aria-label="Remover archivo">&times;</button>
            `;
            fileList.appendChild(item);
        });

        processBtn.disabled = selectedFiles.length === 0;
    }

    // --- Form Submission ---
    processBtn.addEventListener("click", async () => {
        if (selectedFiles.length === 0) return;

        setLoadingState(true);
        hideStatus();

        try {
            const formData = new FormData();
            selectedFiles.forEach(file => formData.append("files", file));

            // Si está en modo update y hay Excel seleccionado, adjuntarlo
            const selectedMode = document.querySelector('input[name="mode"]:checked').value;
            if (selectedMode === "update" && excelFile.files[0]) {
                formData.append("existing_excel", excelFile.files[0]);
            }

            const response = await fetch("http://127.0.0.1:8000/process", {
                method: "POST",
                body: formData
            });

            if (!response.ok) {
                let errorMsg = "Error al procesar los archivos en el servidor.";
                try {
                    const errorData = await response.json();
                    errorMsg = errorData.detail || errorData.message || errorMsg;
                } catch (e) { }
                throw new Error(errorMsg);
            }

            // Descarga automática del PDF/Excel retornado
            const blob = await response.blob();

            // Intentar extraer el nombre del archivo del header Content-Disposition
            const contentDisposition = response.headers.get('Content-Disposition');
            let filename = "Papeles_de_Trabajo_F931.xlsx";
            if (contentDisposition && contentDisposition.includes('filename=')) {
                const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
                if (filenameMatch && filenameMatch.length === 2) {
                    filename = filenameMatch[1];
                }
            }

            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = downloadUrl;
            a.download = filename;

            document.body.appendChild(a);
            a.click();

            // Clean up
            window.URL.revokeObjectURL(downloadUrl);
            a.remove();

            showStatus("¡Procesamiento exitoso! La descarga ha comenzado.", "success");

            // Limpiar la lista de archivos después del éxito
            selectedFiles = [];
            updateFileList();

        } catch (error) {
            console.error(error);
            showStatus(error.message || "Hubo un error de conexión con el servidor.", "error");
        } finally {
            setLoadingState(false);
        }
    });

    function setLoadingState(isLoading) {
        processBtn.disabled = isLoading || selectedFiles.length === 0;
        btnText.style.display = isLoading ? "none" : "block";
        btnLoader.style.display = isLoading ? "block" : "none";

        // Disable file dropzone interaction during loading
        dropArea.style.pointerEvents = isLoading ? "none" : "auto";
        const removeBtns = document.querySelectorAll(".file-remove");
        removeBtns.forEach(btn => btn.disabled = isLoading);
    }

    function showStatus(message, type) {
        statusAlert.className = `status-alert status-${type}`;
        statusAlert.innerText = message;
        statusAlert.style.display = "block";
    }

    function hideStatus() {
        statusAlert.style.display = "none";
    }
});