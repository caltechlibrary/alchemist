{% extends "base.tpl" %}
{% block viewer %}
      <video style="width:100%" controls>
        <source src="{{ video_url }}" type="video/mp4" />
      </video>
{% endblock %}
