# apps/accounts/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    fields = ['role', 'language']
    verbose_name_plural = 'Role & Language'


# Re-register User with the profile inline. Note: Role is applied after
# the "Staff status" checkbox when both are saved together, so Role wins
# (UserProfile.save() keeps is_staff in sync with it).
admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]
    list_display = BaseUserAdmin.list_display + ('get_role',)

    def get_inline_instances(self, request, obj=None):
        # On the add page the post_save signal creates the profile; an
        # inline there would try to create a second one (OneToOne clash).
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)

    @admin.display(description='Role', ordering='profile__role')
    def get_role(self, obj):
        profile = getattr(obj, 'profile', None)
        return profile.get_role_display() if profile else '—'


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display  = ['user', 'role', 'language']
    list_filter   = ['role', 'language']
    search_fields = ['user__username']
