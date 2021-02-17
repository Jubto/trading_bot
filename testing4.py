if not False:
    print('testsetst')

f = 'INJBTC_4h.csv'
if 'BTC' in f:
    print('tttt')

if None:
    print('tes')

d = {5:200000, 1:2, 2:20, 3:200}
print(d.keys())

if 6 not in d.keys():
    print('test')


print(1612263600000 - 1612260000000)
print(1612267200000 + 3600000)
import time
from datetime import datetime,timezone
now_utc = datetime.now(timezone.utc)
print(now_utc)
print(datetime.utcnow())
print(datetime.utcnow().replace(tzinfo=timezone.utc))
print(time.time())
t = str(1613552400000)
print(time.time() - int(t[:-3]))
print(time.time() - int(str(1613552400000)[:-3]))