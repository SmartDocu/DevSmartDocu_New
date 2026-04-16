# Project 에서 App 추가히기 - App 이름 'llm'

### 앱 생성
    - > python manage.py startapp llm
    - config/settings.py 에 앱 등록
        - INSTALLED_APPS = [
            ..., 
            'pages', 
            'llm',
          ]
    - url 연결
        - llm/urls.py
```python
# llm/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='llm_index'),
]
```
        - config/urls.py에 include
            - urlpatterns = [
                path('admin/', admin,site.urls),
                path('llm/', indclude('llm.urls')),
                path('', include('pages.urls')),
              ]


### 앱 작성
    - html 작성
        - llm/templates/llm/chat_sentence.html 작성
    - views.py 작성
        - llm/views.py 작성
    - url 연결
        - llm/urls.py
        - urlpatterns 에 path 추가 : "path('chat_sentence/', views.chat_sentence, name='chat_sentence'),"
