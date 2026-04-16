from django.shortcuts import render

def popup_test(request):
    return render(request, 'pages/popup/popup_test.html')
