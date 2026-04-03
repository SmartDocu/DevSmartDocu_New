# app/core/settings.py

# 기본값
DEFAULT_MAX_TABS = 5
DEFAULT_LANG = 'ko'

# 메뉴 기본 구조 (권한별 필터링용)
# app/core/settings.py

MENU_STRUCTURE = [
    {
        "key": "home",
        "label": "menu.Home",
        "requiresAuth": False,
        "menu": "Home"  # React에서 매핑할 키
    },
    {
        "key": "group1",
        "label": "menu.master_data",
        "requiresAuth": True,
        "children": [
            {
                "key": "master_docs",
                "label": "menu.master_data.master_docs",
                "requiresAuth": True,
                "menu": "master_docs"  # React에서 매핑
            }
        ],
    }
]

def filter_menu_for_role(menu_list, user_role=None, is_logged_in=False):
    result = []

    for item in menu_list:
        if item.get("requiresAuth") and not is_logged_in:
            continue

        if "roles" in item and user_role not in item["roles"]:
            continue

        new_item = item.copy()

        if item.get("children"):
            new_item["children"] = filter_menu_for_role(
                item["children"], user_role, is_logged_in
            )

        result.append(new_item)

    return result

def get_user_default_lang(user_record):
    """사용자 DB 레코드에서 언어 가져오기, 없으면 기본값 반환"""
    return user_record.get("lang") or DEFAULT_LANG