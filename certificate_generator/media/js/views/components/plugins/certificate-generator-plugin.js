import ko from "knockout";
import template from "templates/views/components/plugins/certificate-generator-plugin.htm";
import "../../../../css/certificate-generator-plugin.css";

const API_BASE = window.location.origin;

function getCookie(name) {
    if (!document.cookie) return null;
    for (let cookie of document.cookie.split(";")) {
        cookie = cookie.trim();
        if (cookie.startsWith(name + "=")) {
            return decodeURIComponent(cookie.slice(name.length + 1));
        }
    }
    return null;
}

function ViewModel() {
    const self = this;

    self.resources = [];
    self.templates = [];
    self.resourceSelect = null;

    self.init = function() {
        self.loadResources();
        self.loadTemplates();
        self.bindHandlers();
    };

    self.loadResources = async function() {
        try {
            const response = await fetch(`${API_BASE}/certificate-generator/get-resources/`);
            const data = await response.json();
            self.resources = data.resources || [];

            if (typeof TomSelect === "undefined") {
                console.warn("TomSelect not loaded yet");
                return;
            }
            self.resourceSelect = new TomSelect("#resourceSelect", {
                placeholder: "Search resources...",
                options: self.resources.map(r => ({
                    value: r.resource_id,
                    text: `${r.place_id || ""} ${r.name || ""}`.trim() || r.resource_id,
                })),
                searchField: ["text"],
                maxOptions: 100,
            });
        } catch (error) {
            console.error("Error loading resources:", error);
            self.showMessage("Failed to load resources: " + error.message, "error");
        }
    };

    self.loadTemplates = async function() {
        try {
            const showAll = document.getElementById("showAllVersions").checked;
            const params = new URLSearchParams();
            if (showAll) {
                params.set("include_archived", "true");
            }

            const response = await fetch(`${API_BASE}/certificate-generator/templates?${params}`);
            const data = await response.json();
            self.templates = data.templates || [];

            const select = document.getElementById("templateSelect");
            select.innerHTML = "";

            if (self.templates.length === 0) {
                const opt = document.createElement("option");
                opt.value = "";
                opt.textContent = "No templates available";
                select.appendChild(opt);
                return;
            }

            const placeholder = document.createElement("option");
            placeholder.value = "";
            placeholder.textContent = "-- Select a template --";
            select.appendChild(placeholder);

            const makeOption = (value, text) => {
                const opt = document.createElement("option");
                opt.value = value;
                opt.textContent = text;
                return opt;
            };

            for (const t of self.templates) {
                if (showAll && t.versions.length > 1) {
                    const group = document.createElement("optgroup");
                    group.label = t.name;
                    for (const v of t.versions) {
                        const label = `v${v.version} (${v.status})`;
                        const desc = v.changelog ? ` - ${v.changelog.substring(0, 50)}` : "";
                        group.appendChild(makeOption(`${t.id}:${v.version}`, label + desc));
                    }
                    select.appendChild(group);
                } else {
                    const pv = t.published_version;
                    const vLabel = pv ? ` (v${pv.version})` : "";
                    const value = pv ? `${t.id}:${pv.version}` : t.id;
                    select.appendChild(makeOption(value, `${t.name}${vLabel}`));
                }
            }
        } catch (error) {
            console.error("Error loading templates:", error);
            self.showMessage("Failed to load templates: " + error.message, "error");
        }
    };

    self.updateTemplateMeta = function(value) {
        const metaDiv = document.getElementById("templateMeta");
        if (!value) {
            metaDiv.replaceChildren();
            return;
        }

        let templateId, versionNum;
        if (value.includes(":")) {
            [templateId, versionNum] = value.split(":");
            versionNum = parseInt(versionNum);
        } else {
            templateId = value;
        }

        const template = self.templates.find(t => t.id === templateId);
        if (!template) return;

        const ver = versionNum
            ? template.versions.find(v => v.version === versionNum)
            : template.published_version;

        if (ver) {
            const sizeKB = (ver.size / 1024).toFixed(1);
            const date = new Date(ver.created_at).toLocaleDateString();
            metaDiv.replaceChildren();

            const strong = document.createElement("strong");
            strong.textContent = `v${ver.version}`;
            metaDiv.appendChild(strong);
            metaDiv.appendChild(document.createTextNode(
                ` (${ver.status}) | Size: ${sizeKB} KB | By: ${ver.created_by} | ${date}`
            ));
            metaDiv.appendChild(document.createElement("br"));

            const em = document.createElement("em");
            em.textContent = ver.changelog || "";
            metaDiv.appendChild(em);
        }
    };

    self.handleSubmit = async function(e) {
        e.preventDefault();

        const resource = document.getElementById("resourceSelect");
        const resourceId = resource.value;
        const resourceName = resource.options[resource.selectedIndex]?.text || "N/A";

        const templateValue = document.getElementById("templateSelect").value;
        let templateId, templateVersion;
        if (templateValue.includes(":")) {
            [templateId, templateVersion] = templateValue.split(":");
            templateVersion = parseInt(templateVersion);
        } else {
            templateId = templateValue;
            templateVersion = null;
        }

        if (!resourceId || !templateId) {
            self.showMessage("Please select both a resource and a template", "error");
            return;
        }

        const btn = document.getElementById("generateBtn");
        const originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span>Generating...';
        self.showMessage("Processing your request...", "info");

        try {
            const response = await fetch(`${API_BASE}/certificate-generator/process-template/`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCookie("csrftoken"),
                },
                body: JSON.stringify({
                    resource_id: resourceId,
                    resource_name: resourceName,
                    template_id: templateId,
                    template_version: templateVersion,
                }),
            });

            if (!response.ok) {
                let errorData = {};
                try {
                    errorData = await response.json();
                } catch (_) { /* response was not JSON */ }
                const parts = [errorData.error, errorData.details].filter(Boolean);
                throw new Error(parts.length ? parts.join(": ") : `Failed to generate document (HTTP ${response.status})`);
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;

            const contentDisposition = response.headers.get("Content-Disposition");
            let filename = "document.docx";
            if (contentDisposition) {
                const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(contentDisposition);
                if (matches && matches[1]) {
                    filename = matches[1].replace(/['"]/g, "");
                }
            }

            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            self.showMessage(`Document generated successfully: ${filename}`, "success");
        } catch (error) {
            console.error("Error generating document:", error);
            self.showMessage("Failed to generate document: " + error.message, "error");
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    };

    self.showMessage = function(message, type) {
        const messageDiv = document.getElementById("statusMessage");
        messageDiv.textContent = message;
        messageDiv.className = `status-message ${type}`;
        messageDiv.style.display = "block";
        if (type === "success") {
            setTimeout(() => { messageDiv.style.display = "none"; }, 5000);
        }
    };

    self.bindHandlers = function() {
        document.getElementById("templateSelect").addEventListener("change", (e) => {
            self.updateTemplateMeta(e.target.value);
        });
        document.getElementById("showAllVersions").addEventListener("change", self.loadTemplates);
        document.getElementById("templateForm").addEventListener("submit", self.handleSubmit);
    };

    // Defer to next tick so the template's DOM exists before we touch it
    setTimeout(self.init, 0);
}

export default ko.components.register("certificate-generator-plugin", {
    viewModel: ViewModel,
    template: template,
});
