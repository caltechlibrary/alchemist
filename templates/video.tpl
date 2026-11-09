{% extends "base.tpl" %}
{% block viewer %}
      {% if video_urls | length > 1 %}
      {% for video_url in video_urls %}
      <figure>
        <figcaption>Part {{ loop.index }} of {{ loop.length }}</figcaption>
        <video style="width:100%" controls preload="metadata">
          <source src="{{ video_url }}" type="video/mp4" />
        </video>
      </figure>
      {% endfor %}
      {% else %}
      <video style="width:100%" controls>
        <source src="{{ video_urls[0] }}" type="video/mp4" />
      </video>
      {% endif %}
{% endblock %}
