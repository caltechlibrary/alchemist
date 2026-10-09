{% extends "base.tpl" %}
{% block viewer %}
      <script>
        // PDF.js's viewer announces itself to a same-origin parent page
        // before it starts, so the page can configure it
        document.addEventListener("webviewerloaded", function (event) {
          const options = event.detail.source.PDFViewerApplicationOptions;
          // never run JavaScript embedded in a PDF
          options.set("enableScripting", false);
          // view only: no highlight, ink, text, or stamp tools
          options.set("annotationEditorMode", -1);
        });
      </script>
      <iframe src="{{ pdf_viewer_url }}" title="{{ title | e }}" style="width:100%;height:80vh;border:0" allowfullscreen></iframe>
{% endblock %}
