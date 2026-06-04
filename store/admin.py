from django.contrib import admin
from .models import (
    Announcement, CartItem, Category, Customer, Feedback,
    PendingSignup, Product, WishlistItem, Order, OrderItem
)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'original_price', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('name',)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('title',)


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ('customer', 'product', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('customer__username', 'product__name')


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('customer', 'product', 'quantity', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('customer__username', 'product__name')


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'rating', 'is_approved', 'created_at')
    list_filter = ('is_approved', 'rating', 'created_at')
    search_fields = ('name', 'email', 'message')

    actions = ['approve_feedback']

    @admin.action(description='Approve selected feedback')
    def approve_feedback(self, request, queryset):
        queryset.update(is_approved=True)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('username', 'email')


@admin.register(PendingSignup)
class PendingSignupAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'is_used', 'created_at', 'expires_at')
    list_filter = ('is_used', 'created_at')
    search_fields = ('username', 'email')


# 🔥 FIXED ORDER ADMIN (TIME FORMAT FIX)
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
    'id',
    'customer',
    'full_name',
    'phone',
    'city',
    'payment_method',
    'status',
    'total_amount',
    'formatted_date'
)
    list_filter = ('payment_method', 'created_at')
    search_fields = ('full_name', 'phone', 'city', 'customer__username')

    def formatted_date(self, obj):
        return obj.created_at.strftime("%d %b %Y, %I:%M %p")
    formatted_date.short_description = 'Order Date'


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'quantity', 'price')
    search_fields = ('product__name', 'order__id')