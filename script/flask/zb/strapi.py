#!/usr/bin/python
#-*- coding: UTF-8 -*-
# FileName : strapi.py
# Author   : Shan
# DateTime : 2019/1/9
# SoftWare : PyCharm
from flask import Blueprint, abort,Flask, request, jsonify, render_template, redirect,url_for, send_file, send_from_directory
import os,json
from werkzeug.utils import secure_filename
import chardet
import time,datetime
import base64
import globalvar as gl
import libdb as libdb

global logger
global CONF

def cookie_csv_parse(line):
    row = line.split(',')
    if len(row) < 3:
        return None

    if row[0] == "" or row[0] == "名称":
        return None

    # 名称,密码,Cookies
    record  = {}
    record['nickname']    = row[0]
    record['password']    = row[1]
    record['cookie']      = row[2]
    return record

def cookie_load(path):
    FILE = open(path, 'rb')
    records =[]
    seq = 0
    for line in FILE:
        if '\xef\xbb\xbf' in line:
            logger.info('用replace替换掉\\xef\\xbb\\xb')
            line = line.replace('\xef\xbb\xbf', '')  # 用replace替换掉'\xef\xbb\xbf'
        line = line.strip('\n')
        cdet = chardet.detect(line)
        if cdet['encoding'].lower().find("utf-8") == 0 :
            u8str = line
        else:
            u8str = line.decode('GBK').encode("utf8")
        record = cookie_csv_parse(u8str)
        if record == None:
            continue

        record['seq'] = seq
        records.append(record)
        seq += 1
    logger.debug("%d cookies loaded from %s!" ,len(records), path)
    return records

def cookieWriteToDB(nickname, pwd, cookie):
    key = "nickname, password, regdate, lastdate, colddate, cookie"
    value = "'%s', '%s', '%d', '%d', '%d', '%s'" % (nickname, pwd, \
                                                    int(time.time()), int(time.time()), \
                                                    int(time.time()), cookie)
    logger.debug('key:%s, value:%s', key, value)
    rv = libdb.LibDB().insert_db(key, value, CONF['database']['table'])
    return rv

def updateFailWriteToDB(nickname, update_fail):
    if update_fail == 'update_fail':
        setval = "update_fail=update_fail+1"
    else:
        return False
    condition = "nickname='%s'" %(nickname)
    logger.debug('setval:%s, condition:%s', setval, condition)
    rv = libdb.LibDB().update_db(setval, condition, CONF['database']['table'])
    return rv

def cookieUpdateToDB(nickname, pwd, cookie):
    setval = "password='%s',lastdate='%d',cookie='%s',update_fail=0" %(pwd, int(time.time()), cookie)
    condition = "nickname='%s'" %(nickname)
    logger.debug('setval:%s, condition:%s', setval, condition)
    rv = libdb.LibDB().update_db(setval, condition, CONF['database']['table'])
    return rv

def writeFileToDB(file):
    """
    将cooikes csv文件写入数据库
    :param file: cookie文件描述符
    :return:   ou  ：字典，包含信息
               ou['data']['num']  :成功数量
               ou['msg']                :信息
               ou['error']              : 0 ok
                                        : 1 写数据库失败
    """
    ou = dict(error=0, data=dict(), msg='ok')
    basepath = os.path.dirname(__file__)  # 当前文件所在路径
    upload_path = os.path.join(basepath, 'uploads', secure_filename(file.filename))  # 注意：没有的文件夹一定要先创建，不然会提示没有该路径
    file.save(upload_path)

    # 读取文件
    logger.debug("upload_path: %s", upload_path)
    records = cookie_load(upload_path)
    logger.debug(records)
    ou['data']['num'] = len(records)

    #写入数据库
    for record in records:
        rv = cookieWriteToDB(record['nickname'], record['password'], record['cookie'])
        if rv != True:
            ou['error'] = 1
            ou['msg']   = '写数据库失败'
    return ou

strapi_bp = Blueprint('strapi', __name__, template_folder='templates/html')

@strapi_bp.route('/upload', methods=['POST', 'GET'])
def upload():
    """
    测试命令：curl -F "file=@/Users/liudeshan/work/studycase/script/flask/zb/2.csv" -X  "POST" http://localhost:8888/strapi/upload
    :return:
    """
    logger.debug('request.method:%s', request.method)
    logger.debug('request.files:%s', request.files['file'])
    if request.method == 'POST':
        #保存文件
        ou = writeFileToDB(request.files['file'])
        if ou['error'] == 0 :
            return redirect(url_for('stradmin.admin'))
        else:
            return json.dumps(ou)

    else:
        return redirect(url_for('stradmin.admin'))


def str_to_timestamp(str):
    timeArray = time.strptime(str, "%Y-%m-%d %H:%M:%S")
    timeStamp = int(time.mktime(timeArray))
    return timeStamp

def http_do_action(action):
    """
    :param action:
    :return:   ou  ：字典，包含信息
               ou['data']['xxx']        :
               ou['msg']                :信息
               ou['error']              : 0 ok
                                        : 1 写数据库失败
                                        : 2 命令字暂不支持
                                        : 3 参数错误
                                        : 4 读数据库失败
    """
    ou = dict(error=0, data=dict(), msg='ok')
    if action == 'queryOneByDate':
        #测试命令：curl -d "action=queryOneByDate&day=2019-1-7" -X POST http://localhost:8889/strapi/http.do
        day = request.form.get('day')
        if day == None:
            ou['error'] = 3
            ou['msg']   = '参数错误'
            return ou
        timestampBegin = str_to_timestamp(day + ' 0:0:0')
        timestampEnd   = str_to_timestamp(day + ' 23:59:59')
        conditon = 'lastdate >= %d and lastdate <= %d and update_fail <= 5' %(timestampBegin, timestampEnd)
        sql = libdb.LibDB().query_one_by_condition(conditon,CONF['database']['table'])
        if sql == False:
            ou['error'] = 4
            ou['msg']   = '读账号信息从数据库失败'
            return ou
        count = libdb.LibDB().query_count_by_condition(conditon, CONF['database']['table'])
        if count == False:
            ou['error'] = 4
            ou['msg']   = '读账号数量从数据库失败'
            return ou
        total = count[0]

        if total == 0:
            data_str = '%d|none' % (total)
        else:
            data_str = '%d|%s|%s|%s' %(total, sql[2], sql[3], sql[9])
        logger.debug('账号信息：%s',data_str)
        data_encryed  = base64.b64encode(data_str)
        ou['msg'] = '获取成功'
        ou['data']['acc'] = data_encryed
    elif action == 'insertOne':
        #测试命令：curl -d "action=insertOne&entry=xxxx" -X POST http://localhost:8889/strapi/http.do
        entry = request.form.get('entry')
        if entry == None:
            ou['error'] = 3
            ou['msg']   = '参数错误'
            return ou
        logger.debug('获取加密前：' + entry)
        str = base64.b64decode(entry)
        logger.debug('解密后：' + str)
        str = str.split('|')
        logger.debug(str)
        rv = cookieWriteToDB(str[0],str[1],str[2])
        if rv != True:
            ou['error'] = 1
            ou['msg']   = '写数据库失败'
            return ou
        ou['data']['num'] = 1
        ou['msg'] = 'insert success'
    elif action == 'queryOneByNickname':
        # 测试命令：curl -d "action=queryOneByNickname&nick=xxxx" -X POST http://localhost:8889/strapi/http.do
        nick = request.form.get('nick')
        if nick == None:
            ou['error'] = 3
            ou['msg']   = '参数错误'
            return ou
        sql = libdb.LibDB().query_one('nickname', nick, CONF['database']['table'])
        if sql == False:
            ou['error'] = 4
            ou['msg']   = '读数据库失败'
            return ou
        if sql == None:
            ou['msg'] = '没有该用户信息'
            t = dict()
            t['id']    = None
            t['uid']   = None
            t['nickname'] = None
            t['password'] = None
            t['regdate']  = None
            t['lastdate'] = None
            t['colddate'] = None
            t['lastip']   = None
            t['usednum']  = None
            t['cookie']   = None
        else:
            ou['msg'] = 'read success'
            t = dict()
            t['id']    = sql[0]
            t['uid']   = sql[1]
            t['nickname'] = sql[2]
            t['password'] = sql[3]
            t['regdate']  = datetime.datetime.fromtimestamp(sql[4])
            t['lastdate'] = datetime.datetime.fromtimestamp(sql[5])
            t['colddate'] = datetime.datetime.fromtimestamp(sql[6])
            t['lastip']   = sql[7]
            t['usednum']  = sql[8]
            t['cookie']   = sql[9]
        ou['data']    = t
    elif action == 'updateOne':
        # 测试命令：curl -d "action=updateOne&entry=xxxx" -X POST http://localhost:8889/strapi/http.do
        entry = request.form.get('entry')
        if entry == None:
            ou['error'] = 3
            ou['msg']   = '参数错误'
            return ou
        logger.debug('获取加密前：' + entry)
        str = base64.b64decode(entry)
        logger.debug('解密后：' + str)
        str = str.split('|')
        logger.debug(str)
        if len(str) == 3:
            rv = cookieUpdateToDB(str[0],str[1],str[2])
        elif len(str) == 2:
            rv = updateFailWriteToDB(str[0], str[1])
        if rv != True:
            ou['error'] = 1
            ou['msg']   = 'updaet DB failed'
            return ou
        ou['data']['num'] = 1
        ou['msg'] = 'update success'
    else:
        ou['error'] = 2
        ou['msg'] = '命令字暂不支持'
        return ou
    return ou

@strapi_bp.route('/http.do',methods=['POST','GET'])
def http_do():
    """
    api 接口

    """
    if request.method != 'POST':
        return 'hello'
    action = request.form.get('action')
    logger.debug('action: %s', action)
    ou = http_do_action(action)
    return jsonify(ou)

logger = gl.get_logger()
CONF   = gl.get_conf()