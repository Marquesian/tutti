from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeDoneView, PasswordChangeView
from django.urls import reverse_lazy
from django.utils.safestring import mark_safe
from django.views.generic import FormView, TemplateView

from members.forms import MyPasswordChangeForm, ProfileForm, SubscribeForm


class ProfileView(LoginRequiredMixin, TemplateView):
    """Displays info on the logged in member."""
    template_name = "members/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        country = self.request.user.person.country
        memberships = self.request.user.groupmembership_set.order_by("-start")
        context.update({
            "country": mark_safe('<img src="{}" alt="{}"> {}'.format(country.flag, country.code, country.name)),
            "current_memberships": memberships.filter(end=None),
            "past_memberships": memberships.filter(end__isnull=False),
            "memberships_start": date(2020, 3, 30),
        })
        return context


class ProfileFormView(LoginRequiredMixin, FormView):
    """Page for editing own contact info."""
    template_name = "members/profile_form.html"
    form_class = ProfileForm
    success_url = reverse_lazy("members:profile")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.request.user.person
        return kwargs

    def form_valid(self, form):
        form.save()
        return super().form_valid(form)


class MyPasswordChangeView(PasswordChangeView):
    template_name = "members/password_change_form.html"
    success_url = reverse_lazy("members:password_change_done")
    form_class = MyPasswordChangeForm


class MyPasswordChangeDoneView(PasswordChangeDoneView):
    template_name = "members/password_change_done.html"


class SubscribeView(FormView):
    template_name = "members/subscribe_form.html"
    form_class = SubscribeForm
    success_url = reverse_lazy('members:subscribe_done')

    def form_valid(self, form):
        form.save()
        return super().form_valid(form)


class SubscribeDoneView(TemplateView):
    template_name = "members/subscribe_form_done.html"
