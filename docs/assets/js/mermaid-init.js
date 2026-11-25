(function () {
  function render() {
    if (typeof mermaid === "undefined") return;
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "loose",
      theme: "base",
      themeVariables: {
        fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
        primaryColor: "#ede9fe",
        primaryTextColor: "#1e1b4b",
        primaryBorderColor: "#7c3aed",
        lineColor: "#64748b",
        secondaryColor: "#fef3c7",
        tertiaryColor: "#f1f5f9"
      },
      flowchart: { curve: "basis", htmlLabels: true },
      sequence: { useMaxWidth: true, wrap: true },
      class: { useMaxWidth: true },
      er: { useMaxWidth: true }
    });
    mermaid.run({ querySelector: ".mermaid" });
  }
  if (typeof document$ !== "undefined") {
    document$.subscribe(render);
  } else {
    document.addEventListener("DOMContentLoaded", render);
  }
})();
