from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.forms import PasswordChangeForm
from django.forms.widgets import RadioSelect
from ldap3.core.exceptions import LDAPInvalidCredentialsResult

from members.models import Person, MembershipRequest, Instrument, User, UsernameValidator
from sync.ldap import get_connection


class ProfileForm(forms.ModelForm):
    """Allows the user to change some of his profile data."""

    class Meta:
        model = Person
        fields = ['email', 'phone_number', 'street', 'postal_code', 'city', 'country', 'preferred_language']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].help_text = ("If you change your email address, "
                                          "members mail will be sent to the new address.")
        # Set fields as required
        for f in ('email', 'phone_number', 'street', 'postal_code', 'city', 'country', 'preferred_language'):
            self.fields[f].required = True


def try_ldap_bind(user, password):
    """Tries to bind (login) on LDAP with given credentials."""
    conn = get_connection()
    conn.user = user
    conn.password = password
    try:
        conn.bind()
    except LDAPInvalidCredentialsResult:
        return False
    finally:
        conn.unbind()
    return True


class MyPasswordChangeForm(PasswordChangeForm):
    """Password change form that verifies old passwords on LDAP."""

    def clean_old_password(self):
        # Passwords that are only set in LDAP have value 'invalid' in Django
        if self.user.password == "invalid":
            # Try LDAP bind
            old_password = self.cleaned_data["old_password"]
            ldap_user = "uid={},ou=people,dc=esmgquadrivium,dc=nl".format(self.user.username)
            if not try_ldap_bind(ldap_user, old_password):
                raise forms.ValidationError(
                    self.error_messages['password_incorrect'],
                    code='password_incorrect',
                )
            # Bind succeeded
            return old_password
        return super().clean_old_password()


class SubscribeForm(forms.ModelForm):
    # These fields are overridden to omit an 'unset' option (--------)
    preferred_language = forms.CharField(widget=RadioSelect(choices=MembershipRequest.PREFERRED_LANGUAGES))
    gender = forms.CharField(widget=RadioSelect(choices=MembershipRequest.GENDER_CHOICES))

    # These fields constitute mandatory checkboxes that are not part of the model
    add_to_chats = forms.MultipleChoiceField(label="I hereby give permission to add me to the announcement WhatsApp "
                                                   "group chats of Vokollage, Ensuite, and/or Auletes when I join those"
                                                   " sub-associations (as indicated in the previous question).",
                                             help_text="When being part of the choir or orchestras, it is important to "
                                                       "join those group chats to receive (last minute) announcements "
                                                       "with information about rehearsals and concerts. Please send an "
                                                       "email to <a href='mailto:secretary@esmgquadrivium.nl'>"
                                                       "secretary@esmgquadrivium.nl</a> directly after filling in this "
                                                       "form if you wish to withdraw your consent.",
                                             choices=(("True", 'Yes'),),
                                             widget=forms.CheckboxSelectMultiple)
    ensure_subscribe = forms.MultipleChoiceField(label="What are your intentions for filling in this form?",
                                                 help_text="Please fill in the other form if you are interested in "
                                                           "Quadrivium and want to receive some more information.",
                                                 choices=(("True", 'I want to be subscribed to Quadrivium'),),
                                                 widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.populate_boolean_fields()
        self.fields['date_of_birth'].input_formats = ('%d-%m-%Y',)
        # In practice we want all these fields required but historically there are People that do not have those values
        # set. Therefore we make these required at the Form level.
        for field in self.Meta.required:
            self.fields[field].required = True

    class Meta:
        model = MembershipRequest
        fields = ['first_name', 'last_name', 'initials', 'email', 'phone_number', 'street', 'postal_code', 'city',
                  'country', 'gender', 'date_of_birth', 'preferred_language', 'field_of_study', 'is_student', 'iban',
                  'tue_card_number', 'remarks', 'sub_association', 'instruments',
                  'photo_video_consent_external_group', 'photo_video_consent_external', 'photo_video_consent_internal',
                  'ensure_subscribe', 'add_to_chats']
        required = ['first_name', 'last_name', 'initials', 'email', 'phone_number', 'street', 'postal_code', 'city',
                    'country', 'gender', 'date_of_birth', 'preferred_language', 'is_student', 'instruments',
                    'photo_video_consent_external_group', 'photo_video_consent_external', 'photo_video_consent_internal',
                    'ensure_subscribe', 'add_to_chats']
        boolean_choices = ['photo_video_consent_external_group', 'photo_video_consent_external',
                           'photo_video_consent_internal', 'is_student']

    # For the boolean choices, the HTML spec does not distinguish between false and unset, which prevents them from
    # being required. Workaround: use placeholders ('Yes'/'No') and explicitly cast them back later in `clean`.
    def populate_boolean_fields(self):
        _labels = {
            field: MembershipRequest._meta.get_field(field).help_text for field in
            ['photo_video_consent_external_group', 'photo_video_consent_external', 'photo_video_consent_internal']
        }
        _help_texts = {
            'photo_video_consent_external_group':
                "By 'group’ we mean large groups, such as pictures of a full orchestra or choir during a concert."
        }
        for field in self.Meta.boolean_choices:
            self.fields[field] = forms.ChoiceField(
                label=_labels.get(field) or self.fields[field].label,
                help_text=_help_texts.get(field),
                choices=(("Yes", "Yes"), ("No", "No")),
                widget=forms.RadioSelect
            )

    def clean(self):
        for field in self.Meta.boolean_choices:
            self.cleaned_data[field] = self.cleaned_data[field] == 'Yes'
        return super(SubscribeForm, self).clean()


class ProcessMembershipRequestForm(forms.Form):
    username = forms.CharField(required=True, label="Username", validators=[UsernameValidator()])
    person_id = forms.CharField(required=True, label="Person ID")
    instruments = forms.ModelMultipleChoiceField(queryset=Instrument.objects.all(),
                                                 widget=FilteredSelectMultiple("Instruments", is_stacked=False),
                                                 required=False)

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('A user with this username already exists. Please provide an unused username.')

    def clean_person_id(self):
        person_id = self.cleaned_data['person_id']
        Person.validate_person_id_unique(person_id)

    class Media:
        css = {
            'all': [
                'admin/css/widgets.css',
                'admin/css/forms.css'
            ]
        }
        js = (
            'admin/js/vendor/jquery/jquery.js',
            'admin/js/jquery.init.js',
            'admin/js/admin/RelatedObjectLookups.js',
        )
