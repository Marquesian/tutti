from django.urls import path

from members.views import MyPasswordChangeDoneView, MyPasswordChangeView, ProfileView, ProfileFormView, SubscribeView, \
    SubscribeDoneView

app_name = "members"

urlpatterns = [
    path('password_change/', MyPasswordChangeView.as_view(), name="password_change"),
    path('password_change/done/', MyPasswordChangeDoneView.as_view(), name="password_change_done"),
    path('info/', ProfileView.as_view(), name="profile"),
    path('info/change/', ProfileFormView.as_view(), name="profile_form"),
    # The member request pages are moved to WordPress
    path('subscribe/', SubscribeView.as_view(), name="subscribe"),
    path('subscribe/done/', SubscribeDoneView.as_view(), name="subscribe_done"),
]
