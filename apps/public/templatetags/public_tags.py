from django import template

register = template.Library()

@register.filter
def replace(value, args):
    old, new = args.split(',')
    return str(value).replace(old.strip(), new.strip())
