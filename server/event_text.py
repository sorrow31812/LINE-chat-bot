import yaml
import requests
from time import time
from random import choice, randint, uniform, sample
from datetime import datetime, timedelta
from hashlib import md5

from api import (
    cfg, text,
    ConfigFile,
    isValueHaveKeys, is_image_and_ready, str2bool, isFloat,
)
from database import db, UserStatus, UserKeyword, UserSettings, MessageLogs
from other import google_shorten_url, google_search, ehentai_search, exhentai_search
from LineBot import bots


#未整理參考
from google_safe_browsing import google_safe_browsing
MessageLogs_texts = yaml.load(open('logs.yaml', 'r', encoding='utf-8-sig'))

UserSettings_temp = ConfigFile('.UserSettings_temp.tmp')


class EventText():
    def __init__(self, **argv):
        self.__dict__.update(**argv)
        self.message = self.message.replace('"', '＂').replace("'", '’').replace(';', '；') #替換一些字元成全型 防SQL注入攻擊
        self.order, *self.value = self.message.split('=')
        self.order = self.order.lower()
        self.key = self.value[0].strip(' \n') if len(self.value) > 0 else None
        self.value = '='.join(self.value[1:]).strip(' \n') if len(self.value) > 1 else None


    def run(self):
        print(self.user_id, '>', self.message)

        t0 = time()
        reply_message = self.index()
        t1 = time() - t0

        #公告
        if reply_message is None:
            reply_message = []
        elif type(reply_message) == str:
            reply_message = [reply_message]
                
        if UserStatus.check_news(self.group_id):
            reply_message.append(''.join([cfg['公告']['ver'], ' ', cfg['公告']['內容']]))

        for mid in [self.user_id, self.group_id]:
            if mid is not None and UserSettings_temp.has_option(mid, '臨時公告'):
                try:
                    user_name = bots[self.bot_id].get_group_member_profile(self.group_id, self.user_id).display_name if mid != self.group_id else ''
                except:
                    user_name = ''
                reply_message.append('<作者回覆%s>\n%s' % (user_name, UserSettings_temp.get(mid, '臨時公告')))
                UserSettings_temp.remove_option(mid, '臨時公告')
                UserSettings_temp.save()

        bots[self.bot_id].reply_message(self.reply_token, reply_message)
        t2 = time() - t1 - t0
        print(self.user_id, '<', reply_message, '(%dms, %dms)' % (t1*1000, t2*1000))

        #刷新時間
        UserStatus.refresh(self.group_id)
        UserStatus.refresh(self.user_id)
        
        db.session.commit()
        return reply_message


    def index(self):
        if   self.order in ['-?', '-h', 'help', '說明', '指令', '命令']:
            return cfg.get('指令說明')
        elif self.order in ['公告']:
            return None
        elif self.order in ['愛醬安靜', '愛醬閉嘴', '愛醬壞壞', '愛醬睡覺']:
            return self.sleep()
        elif self.order in ['愛醬講話', '愛醬說話', '愛醬聊天', '愛醬乖乖', '愛醬起床', '愛醬起來']:
            return self.wake_up()
        elif self.order in ['-l', 'list', '列表']:
            return self.list()
        elif self.order in ['-a', 'add', 'keyword', '新增', '關鍵字', '學習']:
            return self.add()
        elif self.order in ['-a+', 'add+', 'keyword+', '新增+', '關鍵字+', '學習+']:
            return self.add_plus()
        elif self.order in ['-d', 'delete', 'del', '刪除', '移除']:
            return self.delete()
        elif self.order in ['-o', 'opinion', '意見', '建議', '回報', '檢舉']:
            return self.opinion()
        elif self.order in ['-s', 'set', 'settings', '設定', '設置']:
            return self.settings()
        elif self.order in ['log', 'logs', '紀錄', '回憶']:
            return self.logs()
        elif self.order in ['google', 'goo']:
            return self.google()
        elif self.order in ['短網址']:
            return self.google_url_shortener()
        elif self.order in ['飆車']:
            return self.bt()
        elif self.order in ['停車', '煞車']:
            return self.bt_stop()
        elif self.order in ['e-hentai', 'ehentai', 'e變態']:
            return self.ehentai()
        elif self.order in ['exhentai', 'ex變態']:
            return self.exhentai()
        else:
            return self.main()


    def sleep(self):
        '''
            愛醬睡覺
        '''
        if self.group_id is None:
            return '...'
        h = 12 if self.key is None or not self.key.isdigit() else int(self.key)
        t = time() + 60 * 60 * (24*7 if h > 24*7 else 1 if h < 1 else h)
        UserSettings_temp.set(self.group_id, '暫停', str(t))
        UserSettings_temp.save()
        return '%s\n(%s)' % (text['睡覺'], datetime.fromtimestamp(t).strftime('%Y-%m-%d %H:%M'))


    def wake_up(self):
        '''
            愛醬起床
        '''
        if self.group_id is None:
            return '...'
        if UserSettings_temp.has_option(self.group_id, '暫停'):
            UserSettings_temp.remove_option(self.group_id, '暫停')
            UserSettings_temp.save()
            return text['睡醒']
        else:
            return text['沒睡']


    def list(self):
        '''
            列出關鍵字
        '''
        MessageLogs.add(self.group_id, self.user_id, nAIset=1) #紀錄次數

        if self.group_id is None or self.key in cfg['詞組']['自己的']:
            if self.user_id is None:
                return text['權限不足']
            else:
                return '、'.join([k.keyword for k in UserKeyword.get(self.user_id)])
        else:
            return '、'.join([k.keyword for k in UserKeyword.get(self.group_id)]) \
                    + '\n\n【列表=我】查詢自己'


    def add(self, plus=False):
        '''
            新增關鍵字
        '''
        MessageLogs.add(self.group_id, self.user_id, nAIset=1) #紀錄次數

        if self.key is None:
            return text['學習說明']

        #文字處理
        self.key = self.key.lower()
        while '***' in self.key: self.key = self.key.replace('***', '**')
        while '|||' in self.key: self.key = self.key.replace('|||', '||')
        while '___' in self.key: self.key = self.key.replace('___', '__')

        #查詢
        if self.value is None or self.value == '':
            reply_message = ['<%s>' % self.key]

            if self.group_id is not None:
                data = UserKeyword.get(self.group_id, self.key)
                if data is not None:
                    reply_message.append('群組=%s' % data.reply)
            
            if self.user_id is not None:
                data = UserKeyword.get(self.user_id, self.key)
                if data is not None:
                    reply_message.append('個人=%s' % data.reply)

            return '\n'.join(reply_message) if len(reply_message) > 1 else '%s<%s>' % (text['關鍵字查詢不到'], key)

        #新增
        ban_key = ['**', '愛醬**', '**愛醬**']
        if self.key in ban_key:
            return '%s\n%s' % (text['關鍵字禁用'], text['分隔符'].join(ban_key))

        if self.key != text['名稱'] and self.key[:2] == text['名稱']:
            self.key = self.key[2:].strip(' \n')
        
        if self.key == '':
            return text['學習說明']

        #保護模式過濾 之後option寫入database將此邏輯合併計算中
        n = self.value.rfind('##')
        if n > -1 and '保護' in self.value[n:] and key[:2] == '**' and key[-2:] == '**':
            return '為了避免過度觸發\n保護模式關鍵字不接受前後**喔'

        reply_message = ['<%s>記住了喔 ' % self.key]

        try:
            if self.group_id is not None and UserKeyword.add_and_update(self.group_id, self.user_id, self.key, self.value, plus=plus):
                reply_message.append('(群組)')

            if self.user_id is not None and UserKeyword.add_and_update(self.user_id, self.user_id, self.key, self.value, plus=plus):
                reply_message.append('(個人)')
            else:
                reply_message.append('(不儲存個人)\n' + text['權限不足'])
        except Exception as e:
            return '學習失敗: %s' + str(e)
            raise e

        level = len(self.key) - self.key.count('**')*(len('**')+1)  #database的UserKeyword.level 懶得改上面
        if level < 0:
            reply_message.append('\n愛醬非常不建議這種會過度觸發的詞喔\n請慎用')
        elif level == 0:
            reply_message.append('\n這種容易觸發的詞容易造成過多訊息喔\n請注意使用')
        elif level >= 7:
            reply_message.append('\n這種詞命中率較低喔 請善加利用萬用字元雙米號')

        for i in self.value.replace('__', '||').split('||'):
            i = i.strip()
            if i[:4] == 'http' and not is_image_and_ready(i):
                reply_message.append('<%s>\n愛醬發現圖片網址是錯誤的\n請使用格式(jpg, png)\n短網址或網頁嵌圖片可能無效\n必須使用https' % i)
            break #如果全部都檢查時間會太久 只幫第一個檢查格式 通常使用者圖床也會使用同一個 應該不會有問題

        #保護模式提醒 之後option寫入database將此邏輯合併計算中
        n = self.value.rfind('##')
        if n > -1 and '保護' in self.value[n:]:
            reply_message.append('\n(此為保護關鍵字 只有你可以刪除及修改 為了避免爭議 建議不要濫用)')
            
        return ''.join(reply_message)


    def add_plus(self):
        '''
            新增關鍵字(疊加)
        '''
        if self.key is None:
            return text['學習說明+']

        return self.add(plus=True)
        
    
    def delete(self):
        '''
            刪除關鍵字
        '''
        MessageLogs.add(self.group_id, self.user_id, nAIset=1) #紀錄次數

        if self.key is None:
            return '格式:\n刪除=<關鍵字>'

        if self.key != text['名稱'] and self.key[:2] == text['名稱']:
            self.key = self.key[2:].strip(' \n')

        reply_message = ['<%s>刪除了喔 ' % (self.key)]

        try:
            if self.group_id is not None and UserKeyword.delete(self.group_id, self.user_id, self.key):
                reply_message.append('(群組)')

            if self.user_id is not None and UserKeyword.delete(self.user_id, self.user_id, self.key):
                reply_message.append('(個人)')
        except Exception as e:
            return '刪除失敗: %s' + str(e)
            raise e
            
        return ''.join(reply_message) if len(reply_message) > 1 else '喵喵喵? 愛醬不記得<%s>' % (self.key)


    def opinion(self):
        '''
            回報、建議、檢舉
        '''
        MessageLogs.add(self.group_id, self.user_id, nAIset=1) #紀錄次數

        if self.key is None:
            return text['回報說明']
        try:
            bots['admin'].send_message(cfg['admin_line'], '%s\n%s\n%s\n%s' % (self.bot_id, self.group_id, self.user_id, self.message))
            return text['回報完成']
        except Exception as e:
            return '訊息傳送失敗..%s' % str(e)


    def settings(self):
        '''
            設定
        '''
        MessageLogs.add(self.group_id, self.user_id, nAIset=1) #紀錄次數

        if self.group_id is None:
            return text['設定無個人提醒']

        if self.key is None:
            return (
                    '設定=別理我=開/關\n'
                    '設定=全回應=開/關\n'
                    '設定=全圖片=開/關(需要全回應)\n'
                    '設定=髒話過濾=開/關\n'
                    '\n'
                    '(不輸入值可查看說明)'
                )
        
        try:
            #全群組
            if self.key == '全回應' or self.key == '愛醬全回應':
                if self.value is None:
                    return '開啟後愛醬開頭的對話將從全部的詞庫中產生反應\n【預設:開】'
                UserSettings.update(self.group_id, None, {'全回應':str2bool(self.value)})
                return '設定完成'
            
            if self.key == '全圖片' or self.key == '愛醬全圖片':
                if self.value is None:
                    return '開啟後全回應的結果包含圖片\n(需要開啟全圖片)\n(注意:圖片沒有任何審核 有可能出現不適圖片 如可接受再開啟)\n【預設:關】'
                UserSettings.update(self.group_id, None, {'全圖片':str2bool(self.value)})
                return '設定完成'

            if self.key == '髒話過濾':
                if self.value is None:
                    return '關閉後回應如果有某些詞可以顯示\n【預設:開】'
                UserSettings.update(self.group_id, None, {'髒話過濾':str2bool(self.value)})
                return '設定完成'

            #群組中個人
            if self.key == '別理我':
                if self.value is None:
                    return '開啟後愛醬不會在此群組對你產生回應\n(愛醬開頭還是可以強制呼叫)\n【預設:關】'
                if self.user_id is None:
                    return text['權限不足']
                UserSettings.update(self.group_id, self.user_id, {'別理我':str2bool(self.value)})
                return '設定完成'

            if self.key == '個人詞庫':
                if self.value is None:
                    return '開啟後會對你的個人詞庫產生回應\n【預設:關】'
                if self.user_id is None:
                    return text['權限不足']
                UserSettings.update(self.group_id, self.user_id, {'個人詞庫':str2bool(self.value)})
                return '設定完成'

            return '沒有此設定喔'
        except Exception as e:
            return '設定錯誤 <%s>' % str(e)

    
    def logs(self):
        '''
            回憶模式
        '''
        if self.group_id is None or self.key in cfg['詞組']['自己的']:
            if self.user_id is None:
                return text['權限不足']

            reply_message = []
            try:
                user_name = bots[self.bot_id].get_group_member_profile(self.group_id, self.user_id).display_name
            except:
                user_name = '你'
            data = MessageLogs.get(user_id=self.user_id)
            reply_message.append('愛醬記得 %s...\n' % user_name)
            reply_message.append('調教愛醬 %s 次' % data['nAIset'])
            reply_message.append('跟愛醬說話 %s 次' % data['nAItrigger'])
            reply_message.append('有 %s 次對話' % data['nText'])
            reply_message.append('有 %s 次貼圖' % data['nSticker'])
            reply_message.append('有 %s 次傳送門' % data['nUrl'])
            reply_message.append('講過 %s 次「幹」' % data['nFuck'])
            reply_message.append('總計 %s 個字\n' % data['nLenght'])
            return '\n'.join(reply_message) + '\n(個人版暫時只能查詢紀錄)'
        else:
            reply_message = []
            if self.key is not None and self.key in cfg['詞組']['全部']:
                data = MessageLogs.get(group_id=self.group_id)
                reply_message.append('愛醬記得這個群組...')
                reply_message.append('有 %s 個人說過話' % data['users'])
                reply_message.append('愛醬被調教 %s 次' % data['nAIset'])
                reply_message.append('跟愛醬說話 %s 次' % data['nAItrigger'])
                reply_message.append('有 %s 次對話' % data['nText'])
                reply_message.append('有 %s 次貼圖' % data['nSticker'])
                reply_message.append('有 %s 次傳送門' % data['nUrl'])
                reply_message.append('講過 %s 次「幹」' % data['nFuck'])
                reply_message.append('總計 %s 個字\n' % data['nLenght'])

            def get_messagelogs_max(MessageLogs_type):
                for row in MessageLogs.query.filter_by(group_id=self.group_id).order_by(eval('MessageLogs.%s' % MessageLogs_type).desc()):
                    if row.user_id is not None:
                        try:
                            user_name = bots[self.bot_id].get_group_member_profile(self.group_id, row.user_id).display_name
                            return [MessageLogs_texts[MessageLogs_type]['基本'].replace('<user>', user_name).replace('<value>', str(eval('row.%s' % MessageLogs_type))),
                                    choice(MessageLogs_texts[MessageLogs_type]['額外'])]
                        except Exception as e:
                            return ['', '讀取錯誤=%s' % str(e)]
                return ['', '']

            rnd = randint(1, 7)
            if   rnd == 1: reply_message_random = get_messagelogs_max('nAIset')
            elif rnd == 2: reply_message_random = get_messagelogs_max('nAItrigger')
            elif rnd == 3: reply_message_random = get_messagelogs_max('nText')
            elif rnd == 4: reply_message_random = get_messagelogs_max('nSticker')
            elif rnd == 5: reply_message_random = get_messagelogs_max('nUrl')
            elif rnd == 6: reply_message_random = get_messagelogs_max('nFuck')
            elif rnd == 7: reply_message_random = get_messagelogs_max('nLenght')
            reply_message.append(reply_message_random[0])

            reply_message.append('(個人紀錄輸入「回憶=我」)\n(完整紀錄輸入「回憶=全部」)')
            return ['\n'.join(reply_message), reply_message_random[1]]


    def google(self):
        '''
            google搜尋
        '''
        if self.key is None:
            return text['google說明']

        MessageLogs.add(self.group_id, self.user_id, nAItrigger=1) #紀錄次數

        return google_search(self.message[self.message.find('='):])

    
    def google_url_shortener(self):
        '''
            google短網址
        '''
        if self.key is None:
            return text['google短網址說明']

        MessageLogs.add(self.group_id, self.user_id, nAItrigger=1) #紀錄次數

        return '愛醬幫你申請短網址了喵\n%s' % google_shorten_url(self.message.replace('短網址=', ''))


    def bt(self):
        '''
            BT直播功能
        '''
        return '目前此功能關閉'


    def bt_stop(self):
        '''
            BT直播功能 停止
        '''
        return '目前此功能關閉'


    def ehentai(self):
        '''
            E變態搜尋
        '''
        MessageLogs.add(self.group_id, self.user_id, nAItrigger=1) #紀錄次數

        if self.group_id is not None:
            return '暫時限制只能在1對1使用喔'
        if self.key is None:
            return text['ehentai說明']
        return ehentai_search(self.key)


    def exhentai(self):
        '''
            EX變態搜尋
        '''
        MessageLogs.add(self.group_id, self.user_id, nAItrigger=1) #紀錄次數

        if self.group_id is not None:
            return '暫時限制只能在1對1使用喔'
        if self.key is None:
            return text['exhentai說明']
        return exhentai_search(self.key)


    def main(self):
        '''
            關鍵字觸發
        '''
        if 'http:' in self.message or 'https:' in self.message: #如果內容含有網址 做網址檢查
            MessageLogs.add(self.group_id, self.user_id, nUrl=1) #紀錄次數
            return google_safe_browsing(self.message)

        self.message = self.message.lower().strip(' \n') #調整內容 以增加觸發命中率
        MessageLogs.add(self.group_id, self.user_id, nText=1, nFuck=(self.message.count('幹') + self.message.count('fuck')), nLenght=len(self.message)) #紀錄次數

        #愛醬開頭可以強制呼叫
        print('ex')
        if self.message != text['名稱'] and self.message[:2] == text['名稱']:
            message_old = self.message
            self.message = self.message[2:].strip(' \n')
            reply_message = self.check(UserKeyword.get(self.group_id))
            if reply_message is not None:
                return reply_message

            reply_message = self.check(UserKeyword.get(self.user_id))
            if reply_message is not None:
                return reply_message
            self.message = message_old #姑且先這樣

        #睡覺模式
        if UserSettings_temp.has_option(self.group_id, '暫停'):
            print(time())
            print(UserSettings_temp.getfloat(self.group_id, '暫停'))
            if time() > UserSettings_temp.getfloat(self.group_id, '暫停'):
                UserSettings_temp.remove_option(self.group_id, '暫停')
                UserSettings_temp.save()
                return text['睡醒']
        else: #一般模式
            if not UserSettings.get(self.group_id, self.user_id, '別理我', False): #檢查不理我模式
                reply_message = self.check(UserKeyword.get(self.group_id))
                if reply_message is not None:
                    return reply_message

                if UserSettings.get(self.group_id, self.user_id, '個人詞庫', False): #檢查是否使用個人詞庫
                    reply_message = self.check(UserKeyword.get(self.user_id))
                    if reply_message is not None:
                        return reply_message

        #全回應模式
        if self.group_id is None or UserSettings.get(self.group_id, None, '全回應', default=True):
            filter_url = self.group_id is None or UserSettings.get(self.group_id, None, '全圖片', default=False)
            if self.message == text['名稱']:
                reply_message = self.check(UserKeyword.get(), exclude_url=not filter_url)
                #reply_message = check(UserKeyword.query, filter_url=not filter_url)
                if reply_message is not None:
                    return reply_message
            if self.message[:2] == text['名稱'] or self.group_id is None:
                if self.message[:2] == text['名稱']: #做兩層是為了方便1對1不見得也要愛醬開頭
                    self.message = self.message[2:].strip(' \n')

                userkeyword_arr = {'>=0':[], '<0':[]}
                for row in UserKeyword.get():
                    if row.author is None:
                        continue
                    if row.level >= 0:
                        userkeyword_arr['>=0'].append(row)
                    else:
                        userkeyword_arr['<0'].append(row)


                reply_message = self.check(userkeyword_arr['>=0'], exclude_url=not filter_url)
                #reply_message = check(UserKeyword.query.filter(UserKeyword.level >= 0), filter_url=not filter_url)
                if reply_message is not None:
                    return reply_message
                else:
                    bots['崩崩崩愛醬'].send_message(cfg['admin_line'], message)
                    reply_message = self.check(userkeyword_arr['<0'], exclude_url=not filter_url)
                    #reply_message = check(UserKeyword.query.filter(UserKeyword.level < 0), filter_url=not filter_url)
                    if reply_message is not None:
                        return reply_message
                    if self.group_id is not None:
                        return '(?)'
        

        if self.group_id is None:
            if self.message[:4] == 'http':
                return '愛醬幫你申請短網址了喵\n%s' % google_shorten_url(message)
            else:
                return '群組指令說明輸入【指令】\n個人服務:\n直接傳給愛醬網址即可產生短網址\n直接傳圖給愛醬即可上傳到圖床\n<1:1自動開啟全回應模式>\n<此功能測試中 字庫還不多>\n<如果開啟全圖片模式有更多回應>\n其他功能如果有建議請使用回報'
        else:
            return None


    def check(self, userkeyword_list, exclude_url=True):
        '''
            關鍵字觸發的邏輯檢查
        '''
        keys = []
        result = []
        for row in userkeyword_list:
            if exclude_url:
                if '@' in row.reply or 'https:' in row.reply: #網址只過濾https 只排除可能是圖片類型的
                    continue
            if row.keyword == self.message:
                result.append(row.reply)
            else:
                keys.append((row.keyword, row.reply))

        if len(result) > 0:
            return self.later(choice(result)) #結果集隨機抽取一個
                
        for k, v in keys:
            try:
                kn = -1
                k_arr = k.split('**')
                for k2 in k_arr:
                    if k2 != '':
                        n = self.message.find(k2)
                        if n > kn:
                            kn = n
                        else:
                            break
                    #最後檢查前後如果為任意字元的情況 那相對的最前最後一個字元必須相等 雖然使用字串會比較精準 暫時先用一個字元 如果**混在中間有可能誤判 但是問題不大
                    if k_arr == '' or k == '': break
                    if k_arr[0] != '' and self.message[0] != k[0]: break
                    if k_arr[-1] != '' and self.message[-1] != k[-1]: break
                else:
                    result.append(v)
            except Exception as e:
                bots['開發部'].send_message(cfg['admin_line'], '錯誤:%s\ngid:%s\nuid:%s\nmsg:%s\nkey:<%s>\n<%s>' % (str(e), self.group_id, self.user_id, self.message, k, v))
        if len(result) > 0:
            return self.later(choice(result)) #結果集隨機抽取一個
        return None


    def later(self, reply_message):
        '''
            關鍵字觸發的後處理
        '''
        MessageLogs.add(self.group_id, self.user_id, nAItrigger=1) #紀錄次數

        #取參數
        opt = {}
        if '##' in reply_message:
            reply_message_new = []
            for i in reply_message.split('##'):
                if '=' in i:
                    a, *b = i.split('=')
                    opt[a] = '='.join(b)
                else:
                    reply_message_new.append(i)
            #reply_message = ''.join(reply_message_new)
            reply_message = reply_message[:reply_message.find('##')] #參數之後會由add儲存至database 這邊之後會廢棄

        filter_fuck = UserSettings.get(self.group_id, None, '髒話過濾', True)
        if filter_fuck and isValueHaveKeys(self.message, cfg['詞組']['髒話']):
            return '愛醬覺得說髒話是不對的!!\n如有需要請使用【設定=髒話過濾=關】關閉'

        #隨機 (算法:比重)
        if '__' in reply_message:
            weight_total = 0
            result_pool = {}
            minimum_pool = []
            for msg in reply_message.split('__'):
                if msg == '':
                    continue

                index = msg.rfind('%')
                if index > -1 and isFloat(msg[index+1:].strip()):
                #if index > -1 and msg[index+1:].strip().isdigit():
                    weight = float(msg[index+1:].strip())
                    msg = msg[:index]
                else:
                    weight = 1
                weight_total += weight

                is_minimum = msg[:1] == '*'
                if is_minimum:
                    is_minimum_pool = msg[:2] == '**'
                    msg = msg[2:] if is_minimum_pool else msg[1:]

                result_pool[msg] = {
                    'weight':weight,
                    'is_minimum':is_minimum,
                }
                if is_minimum and is_minimum_pool:
                    minimum_pool.append(msg)

            if opt.get('百分比', '0').isdigit(): #百分比隨機模式
                number = int(opt.get('百分比', '0'))
                if number > 0:
                    reply_message = []
                    total = 100.0

                    if number > len(result_pool):
                        number = len(result_pool)
                    result_pool = sample([msg for msg, msg_opt in result_pool.items()], number)

                    n = 0
                    for msg in result_pool:
                        n += 1
                        if n >= number or n >= len(result_pool):
                            ratio = total
                            total = 0
                        else:
                            ratio = uniform(0, total)
                            total -= ratio
                        reply_message.append('%s（%3.2f％）' % (msg, ratio))
                        if total <= 0:
                            break

                    return '\n'.join(reply_message)

            count = int(self.message[self.message.rfind('*')+1:]) if '*' in self.message and self.message[self.message.rfind('*')+1:].isdigit() else 1
            if count > 10000: count = 10000
            if count <  1: count = 1
            if count == 1 and '種子' in opt and opt['種子'].isdigit() and int(opt['種子']) > 0:
                seed_time = int((datetime.now()-datetime(2017,1,1)).days * 24 / int(opt['種子']))
                seed = int(md5((str(user_id) + str(seed_time)).encode()).hexdigest().encode(), 16) % weight_total
            else:
                try:
                    #random.org的隨機據說為真隨機
                    if count > 1:
                        r = requests.get('https://www.random.org/integers/?num=%s&min=0&max=%s&col=1&base=10&format=plain&rnd=new' % (count, int(weight_total)), timeout=3)
                        if 'Error' in r.text:
                            raise
                        seed = r.text.split('\n')[:-1]
                    else:
                        raise
                except:
                    seed = [uniform(0, int(weight_total)) for i in range(count)]

            minimum_count = 0
            minimum_index = int(opt.get('保底', 10))
            reply_message_new = {}
            reply_message_image = []
            for i in range(count):
                #r = uniform(0, weight_total) if seed == -1 else seed
                r = float(seed[i]) if type(seed) == list else seed
                for msg, msg_opt in result_pool.items():
                    if r > msg_opt['weight']:
                        r -= msg_opt['weight']
                    else:
                        minimum_count = 0 if msg_opt['is_minimum'] else minimum_count + 1
                        if minimum_count >= minimum_index and len(minimum_pool) > 0:
                            minimum_count = 0
                            msg = choice(minimum_pool)
                        if msg[:6] == 'https:':
                            reply_message_image.append(msg)
                            if len(reply_message_image) > 5:
                                break
                        else:
                            reply_message_new[msg] = (reply_message_new[msg] + 1) if msg in reply_message_new else 1
                        break
                    
            if len(reply_message_new) > 0:
                if count == 1:
                    reply_message = list(reply_message_new.keys())
                else:
                    reply_message = []
                    for msg, num in reply_message_new.items():
                        reply_message.append('%s x %s' % (msg, num))
                    reply_message = ['\n'.join(reply_message)]
            else:
                reply_message = []
            reply_message.extend(reply_message_image[:5])
                
        #這邊有待優化
        if type(reply_message) == str:
            reply_message = [reply_message]
        reply_message_new = []
        for msg in reply_message:
            for msg_split in msg.split('||'):
                reply_message_new.append(msg_split)
        return reply_message_new

