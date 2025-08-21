from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.forms import UserChangeForm, AdminPasswordChangeForm
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse, path
from import_export.admin import ImportExportMixin

from members.adminresources import PersonResource
from members.forms import ProcessMembershipRequestForm
from members.models import User, QGroup, Person, Instrument, Key, ExternalCard, \
    ExternalCardLoan, GroupMembership, PersonTreasurerFields, MembershipRequest

# We need to keep the Django group admin registered, because it sets the ordering.
# admin.site.unregister(Group)
admin.site.register(User, UserAdmin)


# External card thingies

class ExternalCardLoanInline(admin.TabularInline):
    """External card loan inline, for person and external card admin pages."""
    model = ExternalCardLoan
    extra = 0
    fields = ('external_card', 'person', 'start', 'end', 'deposit_made')
    readonly_fields = ()
    autocomplete_fields = ('person',)
    show_change_link = True

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExternalCardLoan)
class ExternalCardLoanAdmin(admin.ModelAdmin):
    """Separate admin page for external card loans."""
    list_display = ('external_card', 'person', 'start', 'end')
    fields = ('external_card', 'person', 'start', 'end', 'deposit_made')
    autocomplete_fields = ('person',)

    def get_readonly_fields(self, request, obj=None):
        """External card, person and start date are only editable during creation."""
        if obj:
            return 'external_card', 'person', 'start'
        else:
            return ()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExternalCard)
class ExternalCardAdmin(admin.ModelAdmin):
    """Admin page for external cards."""
    fields = ('card_number', 'reference_number', 'description')
    inlines = (ExternalCardLoanInline,)


# Group membership inlines

class GroupMembershipInline(admin.TabularInline):
    """Inline for viewing group memberships."""
    model = GroupMembership
    fields = ('group', 'user', 'start', 'end')

    # ordering = ('end', 'start')  # Todo optionally specify ordering

    def has_add_permission(self, request, obj):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class CurrentGroupMembershipInline(GroupMembershipInline):
    """Inline for viewing current group memberships."""
    fields = ('group', 'user', 'start')

    def get_queryset(self, request):
        # Filter for memberships without end date
        return super().get_queryset(request).filter(end=None)


# QGroup

class QGroupModelForm(forms.ModelForm):
    """Group form with a field for group members.

    We can't directly use the `user_set` attribute from the `User.groups`
    attribute because it is linked to the `Group` model and not to `QGroup`.
    Therefore we need to use a custom field.
    """

    group_members = forms.ModelMultipleChoiceField(
        queryset=Person.objects.all(),
        widget=FilteredSelectMultiple(
            verbose_name='people',
            is_stacked=False),  # Horizontal widget
        required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:  # When creating a new group, this will be False
            self.fields['group_members'].initial = self.instance.user_set.all()

    def _save_m2m(self):
        """See superclass method, additionally saves the group members."""
        # A bit ugly to override the private method _save_m2m here.
        # Alternatively it is possible to wrap the save_m2m function from the
        # superclass but that is way more verbose.
        super()._save_m2m()
        self.instance.user_set.set(self.cleaned_data['group_members'])

    class Meta:
        fields = ('group_members',)
        model = QGroup
        help_texts = {
            "name": "Can't be changed after creation. To change a group name, create a new group."
        }


@admin.register(QGroup)
class QGroupAdmin(GroupAdmin):
    form = QGroupModelForm

    fields = ('name', 'description', 'group_members', 'email', 'owner', 'end_on_unsubscribe', 'show_in_overview',
              'category', 'permissions')
    autocomplete_fields = ('owner',)
    list_display = ('name', 'description', 'category')
    list_filter = ('category',)

    inlines = (CurrentGroupMembershipInline,)

    def get_readonly_fields(self, request, obj=None):
        """Makes name field readonly.

        This is because name changes do not propagate correctly to SharePoint.
        Instead it is better to recreate a group to change the name.
        """
        if obj:
            return ["name"]
        else:
            return []


# Person


class MemberListFilter(SimpleListFilter):
    """Filter for Quadrivium memberships.

    By default, filters people that are a member.
    """

    # Text shown in the right panel
    title = "membership"

    # Name used for the URL query parameter
    parameter_name = 'is_member'

    def lookups(self, request, model_admin):
        # Returns the available options
        return (
            (None, "Is a member"),
            ('no', "Is not a member"),
            ('all', "All"),
        )

    def queryset(self, request, queryset):
        if self.value() == 'no':
            # Subtract members from the queryset
            return queryset.filter(~Q(groups=settings.MEMBERS_GROUP))
        elif self.value() is None:
            # Only include members
            return queryset.filter_members()

    def choices(self, changelist):
        for lookup, title in self.lookup_choices:
            yield {
                'selected': self.value() == lookup,
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display': title,
            }


class PersonAdmin(admin.ModelAdmin):
    fieldsets = (
        (None, {
            'fields': ('username', "password")
        }),
        ("Personal info", {
            "fields": (('first_name', 'last_name'), 'initials', 'email', 'groups')
        }),
        ('Contact details', {
            'fields': ('phone_number', 'street', 'postal_code', 'city', 'country')
        }),
        ('Personal info', {
            'fields': ('gender', 'date_of_birth', 'preferred_language', 'instruments', 'field_of_study')
        }),
        ('Quadrivium', {
            'fields': (
                "photo_video_consent_internal",
                "photo_video_consent_external_group",
                "photo_video_consent_external",
                'person_id', 'is_student', ('iban', 'sepa_direct_debit', 'sepa_sign_date'),
                'bhv_certificate', 'notes')
        }),
        ('TU/e', {
            'fields': ('tue_card_number', 'key_access', ('keywatcher_id', 'keywatcher_pin'))
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    readonly_fields = ('last_login', 'date_joined')
    list_display = ('username', 'first_name', 'last_name', 'email', 'is_member')
    list_filter = (
        MemberListFilter,
        'groups',
        'photo_video_consent_internal',
        'photo_video_consent_external_group',
        'photo_video_consent_external',
        'instruments'
    )
    list_max_show_all = 1000
    search_fields = ('username', 'first_name', 'last_name', 'email',
                     'initials', 'phone_number',
                     'street', 'postal_code', 'city', 'instruments__name',
                     'person_id', 'iban', 'notes')
    ordering = ('username',)
    filter_horizontal = ('instruments', 'key_access', 'groups')

    inlines = (ExternalCardLoanInline, GroupMembershipInline)
    save_on_top = True

    form = UserChangeForm  # Needed for the username and password fields/widgets

    # Needed for UserAdmin.user_change_password
    change_password_form = AdminPasswordChangeForm
    change_user_password_template = None

    # def member_start(self, obj: Person):
    #     """List filter that displays the start date of membership."""
    #     try:
    #         m = GroupMembership.objects.get(group=settings.MEMBERS_GROUP, user=obj)
    #         return m.start
    #     except GroupMembership.DoesNotExist:
    #         return None
    #
    # def member_end(self, obj: Person):
    #     """List filter that displays the end date of membership."""
    #     try:
    #         m = GroupMembership.objects.get(group=settings.MEMBERS_GROUP, user=obj)
    #         return m.end
    #     except GroupMembership.DoesNotExist:
    #         return None

    def lookup_allowed(self, lookup, value):
        # Don't allow lookups involving passwords.
        # return not lookup.startswith('password') and super().lookup_allowed(lookup, value)
        # But do allow the rest, so that we can create some cool queries in the address bar
        return not lookup.startswith('password')

    def get_urls(self):
        # Add unsubscribe URL
        return [path('<id>/unsubscribe/',
                     self.admin_site.admin_view(self.unsubscribe_view),
                     name='members_person_unsubscribe',
                     ),
                path('<id>/password/',
                     # Trick from here: https://stackoverflow.com/a/1015405
                     self.admin_site.admin_view(UserAdmin.user_change_password.__get__(self, PersonAdmin)),
                     name='members_person_password_change',
                     ),
                ] + super().get_urls()

    def unsubscribe_view(self, request, id, *args, **kwargs):
        """View for person unsubscribed, removes the person from groups on POST."""
        person = self.get_object(request, id)  # type: Person
        if not self.has_change_permission(request, person):
            raise PermissionDenied
        if person is None:
            raise Http404

        groups_removed = person.groups.filter(qgroup__end_on_unsubscribe=True)
        groups_kept = person.groups.difference(groups_removed)
        if request.POST:
            # Do actual group removal
            person.groups.remove(*groups_removed)
            self.message_user(request,
                              'Person “{}” has been removed from the internal groups.'.format(person.get_full_name()),
                              messages.SUCCESS)
            return HttpResponseRedirect(reverse('admin:members_person_change', args=(person.pk,)))

        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': 'Unsubscribe person',
            'object': person,
            'groups_removed': groups_removed,
            'groups_kept': groups_kept,
            'keys': [k.number for k in person.key_access.all()]  # Would be nicer to have this in template only
        }
        return TemplateResponse(request, 'admin/members/person/unsubscribe.html', context)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        # Password can only be set after creation.
        # Kinda ugly but we need to always change the object because we change the original instance variable
        fieldsets[0][1]["fields"] = ("username",) if not obj else ("username", "password")
        return fieldsets

    def populate_form_from_membership_request(self, form, membership_request):
        msr_attributes = {field.name for field in MembershipRequest._meta.get_fields()}
        person_attributes = {field.name for field in self.model._meta.get_fields()}

        for common_attribute in msr_attributes & person_attributes - {'id'}:
            form.base_fields[common_attribute].initial = getattr(membership_request, common_attribute)

        # Ideally we wouldn't need to hardcode the sub associations. For now™ we mitigate by soft-failing.
        qgroup_names = ['Huidige leden']
        qgroup_names += [MembershipRequest.QGROUP_MAPPER[sa] for sa in membership_request.sub_association]
        qgroups = [qgroup.pk for qgroup in QGroup.objects.filter(name__in=qgroup_names)]
        form.base_fields['groups'].initial = qgroups

    def get_form(self, request, obj=None, **kwargs):
        form = super(PersonAdmin, self).get_form(request, obj, **kwargs)
        if 'membership_request' in request.GET:
            key = request.GET['membership_request']
            membership_request = MembershipRequest.objects.get(pk=key)
            self.populate_form_from_membership_request(form, membership_request)
        return form

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if 'membership_request' in request.GET:
            key = request.GET['membership_request']
            membership_request = MembershipRequest.objects.get(pk=key)
            membership_request.processed = True
            membership_request.save()


@admin.register(Person)
class PersonImportExportAdmin(ImportExportMixin, PersonAdmin):
    """PersonAdmin extended with import/export capabilities."""
    resource_class = PersonResource  # Import/export settings

    def has_import_permission(self, request):
        # Only allow import if user has change+add+delete permission
        return request.user.has_perms(['members.add_person', 'members.change_person', 'members.delete_person'])

    def has_export_permission(self, request):
        return request.user.has_perm('members.view_person')


@admin.register(PersonTreasurerFields)
class PersonTreasurerFieldsAdmin(admin.ModelAdmin):
    """Separate admin for specific treasurer fields only."""
    fields = ("username", 'person_id', 'is_student', 'iban', 'sepa_direct_debit', 'sepa_sign_date',)
    readonly_fields = ("username",)
    list_display = ('username', 'first_name', 'last_name', 'email')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('username',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Instrument)
admin.site.register(Key)


@admin.register(MembershipRequest)
class MembershipRequestAdmin(admin.ModelAdmin):
    form_fields = (
        'first_name', 'last_name', 'email', 'phone_number', 'instruments', 'initials', 'street', 'postal_code',
        'city', 'country', 'gender', 'date_of_birth', 'preferred_language', 'is_student', 'field_of_study', 'iban',
        'tue_card_number', 'sub_association', 'photo_video_consent_internal', 'photo_video_consent_external_group',
        'photo_video_consent_external', 'remarks')
    other_fields = ('date', 'processed')
    fieldsets = ((None, {'fields': form_fields}), ("Meta", {'fields': other_fields}))
    readonly_fields = form_fields + ('date',)
    list_display = ('last_name', 'first_name', 'email', 'instruments', 'date', 'processed')
    ordering = ('-date',)
    list_filter = ('processed',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_urls(self):
        base_name = f"{self.opts.app_label}_{self.opts.model_name}"
        return [
            path("<int:pk>/register/", self.admin_site.admin_view(self.register_view), name=f"{base_name}_register"),
            path("<int:pk>/ignore/", self.admin_site.admin_view(self.ignore_view), name=f"{base_name}_ignore"),
        ] + super().get_urls()

    def register_view(self, request, pk):
        membership_request = MembershipRequest.objects.get(pk=pk)
        if request.method == "POST":
            form = ProcessMembershipRequestForm(request.POST)
            if form.is_valid():
                # Moving on to person_add with prepopulated fields.
                data = f"&username={request.POST['username']}&person_id={request.POST['person_id']}"
                instruments = request.POST.getlist('instruments')
                if instruments:
                    data += f"&instruments={','.join(instruments)}"
                return redirect(reverse("admin:members_person_add") + "?membership_request=" + str(pk) + data)
        else:
            def _sanitize(s):
                return ''.join(filter(str.isalnum, s))
            username = _sanitize(membership_request.initials + membership_request.last_name).lower()
            person_id = _sanitize(membership_request.first_name)[:3] + _sanitize(membership_request.last_name)[:3]
            person_id = person_id.upper().ljust(6, 'X')
            form = ProcessMembershipRequestForm(initial=dict(
                username=username,
                person_id=person_id
            ))

        context = dict(
            self.admin_site.each_context(request),
            object=membership_request,
            opts=MembershipRequest._meta,
            form=form,
            title="Check computed values",
            can_add_instruments=request.user.has_perm('members.add_instrument'),
        )
        return TemplateResponse(request, "admin/members/membershiprequest/register.html", context)

    def ignore_view(self, request, pk):
        membership_request = MembershipRequest.objects.get(pk=pk)

        if request.method == "POST":
            membership_request.processed = True
            membership_request.save()
            return redirect("admin:members_membershiprequest_changelist")

        context = dict(
            self.admin_site.each_context(request),
            object=membership_request,
            opts=MembershipRequest._meta,
            title="Are you sure?",
        )
        return TemplateResponse(request, "admin/members/membershiprequest/ignore.html", context)
