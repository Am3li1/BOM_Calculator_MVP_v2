from django.urls import path
from . import views, views_submissions

app_name = 'bom'

urlpatterns = [
    # Standard BOM
    path('<int:product_pk>/',        views.bom_list,          name='list'),
    path('<int:product_pk>/add/',    views.bom_add,           name='add'),
    path('item/<int:pk>/remove/',    views.bom_remove,        name='remove'),
    path('item/<int:pk>/edit-qty/',  views.bom_edit_quantity, name='edit_qty'),

    # Wood Parts
    path('<int:product_pk>/wood/add/',      views.woodpart_add,    name='wood_add'),
     path('wood/<int:pk>/edit/',         views.woodpart_edit,     name='wood_edit'),
    path('wood/<int:pk>/remove/',           views.woodpart_remove, name='wood_remove'),

    # Voice assistant (stages a draft; only assistant_commit writes)
    path('<int:product_pk>/assistant/turn/',       views.assistant_turn,       name='assistant_turn'),
    path('<int:product_pk>/assistant/remove-row/', views.assistant_remove_row, name='assistant_remove_row'),
    path('<int:product_pk>/assistant/reset/',      views.assistant_reset,      name='assistant_reset'),
    path('<int:product_pk>/assistant/commit/',     views.assistant_commit,     name='assistant_commit'),

    # Carpenter submissions (magic link → admin review → BOM)
    path('submissions/',                           views_submissions.submission_list,        name='submission_list'),
    path('submissions/new/',                       views_submissions.submission_link_create, name='submission_link_create_new'),
    path('<int:product_pk>/submissions/new/',      views_submissions.submission_link_create, name='submission_link_create'),
    path('submissions/<int:pk>/',                  views_submissions.submission_detail,      name='submission_detail'),
    path('submissions/<int:pk>/approve/',          views_submissions.submission_approve,     name='submission_approve'),
    path('submissions/<int:pk>/reject/',           views_submissions.submission_reject,      name='submission_reject'),
    path('submissions/<int:pk>/revoke/',           views_submissions.submission_revoke,      name='submission_revoke'),
]
