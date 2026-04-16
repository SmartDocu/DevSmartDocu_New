from django.shortcuts import render
import os
from django.http import JsonResponse
import json

from utilsPrj.supabase_client import get_supabase_client
from utilsPrj.crypto_helper import encrypt_value, decrypt_value

def master_servers(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")

    supabase = get_supabase_client(access_token, refresh_token)

    user = request.session.get("user")
    tenantid = user.get("tenantid")

    dbconnectors_resp = supabase.schema("smartdoc").table("dbconnectors").select("*").eq("tenantid",tenantid).order("orderno").execute()
    dbconnectors = dbconnectors_resp.data if dbconnectors_resp.data else []

    for connector in dbconnectors:
        try:
            # 복호화 처리 (값이 존재할 경우에만)
            connector["decendpoint"] = decrypt_value(connector.get("encendpoint", "")) if connector.get("encendpoint") else ""
            connector["decdatabase"] = decrypt_value(connector.get("encaccessdb", "")) if connector.get("encaccessdb") else ""
            connector["decuserid"] = decrypt_value(connector.get("encaccessuserid", "")) if connector.get("encaccessuserid") else ""
            connector["decpassword"] = decrypt_value(connector.get("encaccesspassword", "")) if connector.get("encaccesspassword") else ""
        except Exception as e:
            connector["decendpoint"] = connector["decdatabase"] = connector["decuserid"] = connector["decpassword"] = ""

    dbtypes = {"MSSQL", "SUPABASE", "ORACLE"}  # 필요 시 추가 가능

    return render(request, 'pages/master_servers.html', {
        'connectors': dbconnectors,
        'dbtypes' : dbtypes,
    })

def master_servers_save(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    try:
        body = request.body.decode("utf-8")
        if not body:
            return JsonResponse({"error": "Empty request body"}, status=400)
        data = json.loads(body)

        connectid = data.get("connectid")
        connectnm = data.get("connectnm", "").strip()
        connecttype = data.get("connecttype")
        orderno = data.get("orderno")
        useyn = data.get("useyn", True)
        endpoint = data.get("encendpoint", "").strip()
        database = data.get("encdatabase", "").strip()
        accessuserid = data.get("encaccessuserid", "").strip()
        accesspassword = data.get("password")

        encendpoint = encrypt_value(endpoint)
        encdatabase = encrypt_value(database) if database else None
        encaccessuserid = encrypt_value(accessuserid) if accessuserid else None
        encaccesspassword = encrypt_value(accesspassword) if accesspassword else None

        try:
            connectid_int = int(connectid)
        except (TypeError, ValueError):
            connectid_int = None

        try:
            orderno = int(orderno)
        except (TypeError, ValueError):
            orderno = None

        user = request.session.get("user")
        user_id = user.get("id")
        tenantid = user.get("tenantid")
        # users = supabase.schema("smartdoc").table("tenantusers") \
        #     .select("tenantid").eq("useruid", user_id).execute()
        # tenantid = users.data[0]['tenantid']

        if connectid_int:
            existing = supabase.schema("smartdoc").table("dbconnectors") \
                .select("*").eq("connectid", connectid_int).execute()

            if existing.data:
                update_fields = {
                    "connectnm": connectnm,
                    "connecttype": connecttype,
                    "orderno": orderno,
                    "useyn": useyn,
                    "encendpoint": encendpoint
                }
                if encdatabase:
                    update_fields["encaccessdb"] = encdatabase
                if encaccessuserid:
                    update_fields["encaccessuserid"] = encaccessuserid
                if encaccesspassword:
                    update_fields["encaccesspassword"] = encaccesspassword

                supabase.schema("smartdoc").table("dbconnectors") \
                    .update(update_fields).eq("connectid", connectid_int).execute()

                return JsonResponse({"status": "updated"})

        insert_data = {
            "connectnm": connectnm,
            "connecttype": connecttype,
            "orderno": orderno,
            "creator": user_id,
            "useyn": useyn,
            "tenantid": tenantid,
            "encendpoint": encendpoint
        }
        if encdatabase:
            insert_data["encaccessdb"] = encdatabase
        if encaccessuserid:
            insert_data["encaccessuserid"] = encaccessuserid
        if encaccesspassword:
            insert_data["encaccesspassword"] = encaccesspassword

        supabase.schema("smartdoc").table("dbconnectors").insert(insert_data).execute()
        return JsonResponse({"status": "inserted"})

    except Exception as e:
        # print("Exception caught:", str(e))
        return JsonResponse({"error": str(e)}, status=500)

    
def master_servers_delete(request):
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    supabase = get_supabase_client(access_token, refresh_token)

    try:
        data = json.loads(request.body)
        connectid = data.get("connectid")

        if not connectid:
            return JsonResponse({"error": "connectid는 필수입니다."}, status=400)

        # 삭제 수행
        supabase.schema("smartdoc").table("dbconnectors") \
            .delete().eq("connectid", connectid).execute()

        return JsonResponse({"status": "ok"})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
