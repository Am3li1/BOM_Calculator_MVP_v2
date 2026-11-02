# apps/carpenter/admin.py
#
# Read-only audit view. Submissions are created, approved and rejected
# through the BOM pages (apps/bom/views_submissions.py), never here.

from django.contrib import admin

from .models import BOMSubmission, SubmissionLine


class SubmissionLineInline(admin.TabularInline):
    model = SubmissionLine
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(BOMSubmission)
class BOMSubmissionAdmin(admin.ModelAdmin):
    list_display = ['product', 'carpenter_name', 'status', 'created_at', 'submitted_at', 'reviewed_by']
    list_filter = ['status']
    search_fields = ['product__product_code', 'product__product_name', 'carpenter_name']
    exclude = ['token']
    inlines = [SubmissionLineInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
