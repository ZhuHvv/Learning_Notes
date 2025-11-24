# Redis Notes

命令行客户端
`redis-cli [options] [commands]`

- 常见options
> -h 127.0.0.1：指定要连接的redis节点的IP地址，默认是127.0.0.1
> -p 6379：指定要连接的redis节点的端口，默认是6379
> -a 123321：指定redis的访问密码

- commands Redis的操作命令
> 例如 ping：与redis服务端做心跳测试，服务端正常会返回pong

## SQL关系型数据库 vs NoSQL非关系型数据库
|              |                           SQL                            |                 NoSQL                  |
| :----------: | :------------------------------------------------------: | :------------------------------------: |
| 数据存储结构 |                    有固定行、列的表格                    |           文档、键值对、图等           |
|  数据关联性  |                       表与表可关联                       |            关联需要人为维护            |
|   数据查询   |                 使用统一SQL语句进行查询                  |             无固定查询语法             |
|     事务     | 支持事务，且必须满足ACID(原子性、一致性、隔离性、持久性) | 或不支持事务、或只需要BASE(最终一致性) |
| 数据存储位置 |                           磁盘                           |                  内存                  |
|    扩展性    |                           垂直                           |                  水平                  |

## Redis特征
1. 键值型，值支持多种不同数据结构
2. 单线程处理命令，每个命令具备原子性
3. 低延迟、速度快 (基于内存、IO多路复用、良好的编码)
4. 支持数据持久化
5. 支持主从集群、分片集群

## Redis通用命令
**官方说明文档：https://redis.ac.cn/docs/latest/commands/**

 常见：
1. KEYS 查看符合模板的所有key，
由于支持模糊匹配，所以当数据量到达一定规模，效率会很低，因此不建议在生产环境设备上使用
- 语法 `KEYS pattern`

- patterns支持模糊匹配
> `?`表示任意单字符；`*`表示若干个任意字符；`^`表示非；`[]`表示框中的某个字符；`a-k`表示从a到k中任意的某个字符
> `h？llo` 与 hello、hallo 和 hxllo 匹配
`h*llo` 匹配 hllo 和 heeeello
`h[ae]llo` 匹配 hello 和 hallo 但不匹配 hillo
`h[^e]llo` 匹配 hallo、hbllo...但不是hello
`h[a-b]Llo` 匹配 hallo  和 hbllo
如果想逐字匹配特殊字符，可以用 `\` 。

2. DEL 删除指定的一个key
- 语法 `DEL key [key ...]`
可接受多个key

-  返回值：整数，被删除的**实际**键数量

3. EXISTS 判断key是否存在
- 语法 `EXISTS key [key ...]`
可接受多个key

- 返回值：整型。参数中指定的`存在的`键的数量

4. EXPIRE 为 key 设置超时时间。超时时间到期后，该 key 将被自动删除
具有关联超时的 key 通常被称为 易失的 (volatile)
- 语法 `EXPIRE key seconds [NX | XX | GT | LT]`
> NX -- 仅当 key 不存在超时时间时才设置超时
XX -- 仅当 key 存在超时时间时才设置超时
GT -- 仅当新的超时时间大于当前超时时间时才设置
LT -- 仅当新的超时时间小于当前超时时间时才设置

5. TTL 返回具有超时的键的剩余生存时间
- 语法 `TTL key`

- 返回值
> 整数回复：TTL（以秒为单位）。
整数回复：如果键存在但没有关联的过期时间，则返回 -1。
整数回复：如果键不存在，则返回 -2。
 
## Redis数据类型
Redis是key-value型数据库，key一般是`String`类型，value类型则不固定

- key允许由多个单词形成层级结构，单词之间用`:`隔开
> 例如： 公司:项目:组:成员

|   类型    |         例子          |
| :-------: | :-------------------: |
| 基本类型  |
|  String   |      hello world      |
|   Hash    | {a:"hello",b:"world"} |
|   List    |     [a->b->c->d]      |
|    Set    |      {A < B < C}      |
| SortedSet |   {A:1, B:2 , C:3}    |
| 特殊类型  |
|    GEO    |     {A:(123,456)}     |
|  BitMap   |     0101011010010     |
| HyperLog  |     0101011010010     |

### String类型
根据格式不同分为三类
底层都是用字节数组形式存储，但编码方式不同，单个字符串表示的value最长512M
1. string 普通字符串
2. int 整数类型，可以做自增、自减操作
3. float 浮点类型，可以做自增、自减操作

#### 常见命令（详情见官方文档）
1. SET 设置键的字符串值，忽略其类型；若键不存在则创建
2. GET 返回键的字符串值
3. MSET 原子地创建或修改一个或多个键的字符串值
4. MGET 原子地返回一个或多个键的字符串值
5. INCR 将键的整数值递增`1`。如果键不存在，则使用`0`作为初始值
6. INCRBY 将键地整数值按指定的`increment`参数递增。如果键不存在，则使用 0 作为初始值
7. INCRBYFLOAT 将键的浮点值按指定的`increment`参数递增。如果键不存在，则使用 0 作为初始值
8. SETNX 仅当键不存在时才设置键的字符串值
9. SETEX 设置键的过期时间和字符串值。若键不存在则创建 

#### 内部实现
1. SDS(简单动态字符串)
- 可保存**文本数据、二进制数据**
> SDS使用`len`属性判断字符串是否结束；
> 所有的SDS API都以`二进制方式`处理SDS存放在`buf[]`数组中的数据；

- 获取字符串长度的时间复杂度为O(1)

- SDS API是安全的，拼接不会缓冲区溢出
> 拼接前会检查空间是否满足，不足会自动扩容

2. 内部编码(encoding)
![](https://cdn.xiaolincoding.com/gh/xiaolincoder/redis/%E6%95%B0%E6%8D%AE%E7%B1%BB%E5%9E%8B/string%E7%BB%93%E6%9E%84.png)

- int
保存二进制64位有符号整数；
字符串对象的**ptr指针直接赋值**为所存整数，不再指向
![](https://cdn.xiaolincoding.com/gh/xiaolincoder/redis/%E6%95%B0%E6%8D%AE%E7%B1%BB%E5%9E%8B/int.png)

- embstr
保存字符串，长度<=32B
用SDS保存
分配**一次**内存，字符串对象和SDS**连续存储**

> - 由于连续分配，所以需要扩容时要重新分配内存，开销大，因此 embstr编码的对象**实际上是只读**的
> - 对 embstr对象执行修改命令，会先转换成raw，再执行

![](https://cdn.xiaolincoding.com/gh/xiaolincoder/redis/%E6%95%B0%E6%8D%AE%E7%B1%BB%E5%9E%8B/embstr.png)

- raw
保存字符串，长度>32B
分配**两次**内存，字符串对象和SDS**分开存**
![](https://cdn.xiaolincoding.com/gh/xiaolincoder/redis/%E6%95%B0%E6%8D%AE%E7%B1%BB%E5%9E%8B/raw.png)

### Hash类型
无序字典，存储键（field）值(value)对

#### 常见命令（详情见官方文档）
1. HSET 创建或修改哈希中字段的值
2. HGET 返回字段的值
3. HMSET 设置多个字段的值
4. HMGET 返回所有字段**的**值
5. HGETALL 返回所有字段**和**值
6. HKEYS 返回所有字段
7. HVALS 返回所有的值
8. HINCRBY 将字段的整数值按指定的`increment`参数递增。若字段不存在，则使用0作为初始值
9. HSETNX 仅当字段不存在时，才设置字段的值

#### 内部实现

##### 7.0版本之前
1. 压缩列表
元素数量小于`512`(默认值，可修改)且每个元素值小于`64B`(默认值，可修改)，

2. 哈希表
否则

##### 7.0版本之后
**listpack**

### List类型
简单的字符串列表，按插入顺序排序，最大长度 `2^32^-1`
可看作双向链表，支持正向检索、反向检索；
特征：有序、元素可重复、插入和删除块、查询速度一般；

#### 常见命令（详情见官方文档）
1. LPUSH 将一个或多个元素**前置**到列表中。若键不存在则创建
2. LPOP 移除并返回列表中第一个元素。若移除的是最后一个元素，则删除列表
3. RPUSH 将一个或多个元素附加到列表中。若键不存在则创建
4. RPOP 移除并返回列表中最后一个元素。若移除的是最后一个元素，则删除列表
5. LRANGE 返回列表中指定范围的元素
6. BLPOP 移除并返回列表中第一个元素。若无元素则阻塞直到可用。若移除的是最后一个元素，则删除列表
7. BRPOP 移除并返回列表中最后一个元素。若无元素则阻塞直到可用。若移除的是最后一个元素，则删除列表

#### 内部实现

##### 3.2版本之前
1. 双向链表
元素数量小于`512`(默认值，可修改)且每个元素值小于`64B`(默认值，可修改)

2. 压缩列表
否则

##### 3.2版本之后
**快表(quicklist)**

### Set类型
无序并唯一的键值集合；
最多存储`2^32^-1`个元素
特征：无序；元素不可重复；查找快；支持交集、并集、差集等功能；

#### 常见命令（详情见官方文档）
1. SADD 向集合添加一个或多个成员。若键不存在则创建
2. SREM 从集合中移除一个或多个成员。若移除了所有成员，则删除集合
3. SCARD 返回集合中的成员数量
4. SISMEMBER 确定成员是否属于集合
5. SMEMBERS 返回集合的所有成员
6. SINTER 返回多个集合的交集
7. SDIFF 返回多个集合的差集
8. SUNION 返回多个集合的并集

#### 内部实现
1. 整数集合
元素都是**整数**且数量小于`512`(默认值，可修改)

2. 哈希表
否则

### ZSet
每个元素都带有一个`score`排序属性，基于该属性对元素排序
特征：可排序、元素不重复、查询速度快

#### 常见命令（详情见官方文档）
1. ZADD 向有序集合添加一个或多个成员，或更新其`score`。若键不存在则创建
2. ZREM 从有序集合中移除一个或多个成员。若移除了所有成员，则删除集合
3. ZSCORE 返回有序集合中成员的`score`
4. ZRANK 返回有序集合中按升序排序的成员索引
5. ZCARD 返回有序集合中的成员数量
6. ZCOUNT 返回有序集合中`score`在给定范围内的成员数量
7. ZINCRBY 怎家有序集合中成员的`score`
8. ZRANGE 返回有序集合中索引范围内的成员
9. ZRANGEBYSCORE 返回有序集合中分数范围内的成员
10. ZDIFF、ZINTER、ZUNION 返回多个有序集合的差集、交集、并集

#### 内部实现
##### 7.0版本之前
1. 压缩列表
元素数量小于`128`且每个元素值小于`64B`

2. 跳表
否则

##### 7.0版本之后
**listpack**

### BitMap


### HyperLog


### GEO


### Stream



## Redis数据结构
![](https://cdn.xiaolincoding.com//mysql/other/a9c3e7dc4ac79363d8eb8eb2290a58e6.png)

### Redis如何存储键值对
- 使用哈希表存储所有键值对
> - 哈希表是个**数组**，
> - 元素是**哈希桶**,存放指向键值对的指针(dictEntry*)

- 数据结构全景图
![](https://cdn.xiaolincoding.com//mysql/other/3c386666e4e7638a07b230ba14b400fe.png)

> - redisDb 结构：表示 **Redis 数据库的结构**，结构体里存放了指向了 dict 结构的指针；
> - dict 结构：存放了 2 个哈希表，正常情况下都是用`哈希表1`，`哈希表2`只有在 **rehash** 的时候才用
> - ditctht 结构：表示**哈希表的结构**，存放数组，数组中的每个元素都是指向一个哈希表节点结构（dictEntry）的指针；
> - dictEntry 结构：表示**哈希表节点的结构**，结构里存放了 **void *key** 和 **void *value** 指针
>   key 只能指向String对象，value可以指向String对象或集合类型对象

- Redis对象
![](https://cdn.xiaolincoding.com//mysql/other/58d3987af2af868dca965193fb27c464.png)
> - type：标识对象**数据类型**
> - encoding：标识对象使用何种**底层数据结构**
>   （个人觉得这个说法不是很严谨，比如String类型的int编码，并没有使用底层的那几种数据结构，而是直接利用存放ptr指针的空间存储整数）
> - ptr：指向底层数据结构的指针

### SDS

![](https://cdn.xiaolincoding.com//mysql/other/516738c4058cdf9109e40a7812ef4239.png "5.0版本SDS数据结构")

> **len** 记录字符长度
> **alloc** 分配给字符数组的空间长度(该字符串的最大容量)
> **flags** 表示SDS类型
> **buf[]** 字节数组，保存实际数据

#### 二进制安全
- 由`len`记录数据长度，不需要`\0`来标记字符串结尾
- buf[]作为字节数组，可存储任何二进制数据
- SDS所有API都以处理二进制的的方式处理数据

#### 不会发生缓冲区溢出
- 通过`alloc-len`计算剩余可用的空间大小
- 当缓冲区剩余空间不足时，Redis会自动扩大SDS空间大小
> - addlen--字符串需要增加的长度；addlen+len=newlen--扩容后的字符串长度；
> - 当 `newlen > alloc - len`
> 1. `newlen < 1 MB` -- 则SDS扩容至 `2*newlen`
> 2. `newlen >= 1 MB` -- 则SDS扩容至 `newlen + 1 MB`
> - 否则，直接使用剩余空间

#### 节省内存空间
- SDS五种类型：sdshdr5、sdshdr8、sdshdr16、sdshdr32、sdshdr64
- 不同类型的`len`、`alloc`数据类型不同，可以灵活存储不同大小的字符串
- Redis使用专门的编译优化来节省内存空间,
  告诉编译器取消结构体在编译过程中的优化对齐，按照**实际占用字节数**进行对齐
> - 在 `struct声明` 加上 **__attribute__ ((packed))**
> > 例如 struct __attribute__((packed)) test2{
> > $~~~~~~~~~~$ char a;
> > $~~~~~~~~~~$ int b;
> >}test2;
> > 默认情况下分配空间时，会进行字节对齐
> > ![](https://cdn.xiaolincoding.com//mysql/other/35820959e8cf4376391c427ed7f81495.png)
> > 而编译优化后，则不会浪费中间3个字节
> > ![](https://cdn.xiaolincoding.com//mysql/other/47e6c8fbc17fd6c89bdfcb5eedaaacff.png)

### 链表

#### 链表节点结构 listNode
![](https://cdn.xiaolincoding.com//mysql/other/4fecbf7f63c73ec284a4821e0bfe2843.png "Redis链表节点数据结构")
void* value存储节点的值

<br />

#### 链表结构 list
$~~~~~~$包括表头指针head、表尾节点tail、表节点数量len 以及可自定义实现的若干函数
![](https://cdn.xiaolincoding.com//mysql/other/cadf797496816eb343a19c2451437f1e.png "Redis链表数据结构")

#### 优势
1. 由于`prev`、`next`指针，获取某节点的前置节点、后继节点时间复杂度O(1)
2. 由于`head`、`tail`指针，获取链表的表头节点、表尾节点时间复杂度O(1)
3. 由于`len`，获取链表节点数量时间复杂度O(1)
4. 因为`value`的类型是`void*`，所以链表节点可以保存不同类型的值

#### 缺陷
1. 节点间内存不连续，因此**无法很好利用CPU缓存**
2. 保存一个链表节点的值都需要一个链表节点结构头的分配，内存开销较大

- 由于缺陷，Redis3.0的list对象在数据量较少的情况下，会使用**压缩列表**
- 但压缩列表存在性能问题，因此在3.2版本引入**quicklist**
- 在5.0版本引入了**listpack**
  
### 压缩列表
内存紧凑型、占用一块**连续的**内存空间 --> 可以利用CPU缓存、对针对不同长度的数据进行相应编码

#### 结构设计
![](https://cdn.xiaolincoding.com//mysql/other/a3b1f6235cf0587115b21312fe60289c.png "Redis压缩列表及其节点数据结构")
> - 由**连续内存块**组成的**顺序型**数据结构
> - **压缩列表结构**
> > **zlbytes** -- 整个表占用的内存字节数
> > **zltail** -- 尾节点（entryN）距离起始地址的**偏移字节量**
> > **zllen** -- 表中节点数量
> > **zlend** -- 标记表的结束点，固定值 `0xFF(255)`
> - **压缩列表节点**
> > **prevlen** -- `前一个节点长度`，方便实现从后向前遍历
> > $~~~~$若 前一节点长度小于**254B** ，则prevlen占用`1B`
> > $~~~~$否则，则prevlen占用`5B`
> > **encoding** -- 当前节点`实际数据`的`类型`、`长度`，主要为 字符串、整数
> > **data** -- 当前节点`实际数据`

![](https://cdn.xiaolincoding.com/gh/xiaolincoder/redis/%E6%95%B0%E6%8D%AE%E7%B1%BB%E5%9E%8B/%E5%8E%8B%E7%BC%A9%E5%88%97%E8%A1%A8%E7%BC%96%E7%A0%81.png "Redis压缩列表元素编码")
图中`content`表示实际数据，即`data`
> - 若数据是**整数**，则 encoding 占用 1B 
> - 若数据为**字符串**，则根据**字符串的长度大小**，encoding 会占用 1/2/5 B

</br>

#### 连锁更新
**在特殊情况下产生的连续多次空间扩展操作**

当压缩列表**新增**或**修改**某个元素时：
1. 若空间不足，则压缩列表需要重新分配空间
2. 插入较大的元素，可能会使后续元素的`prevlen`空间大小发生变化，导致每个需要修改的元素都要**重新分配空间**

</br>

示例：
- 初始压缩列表，各个节点长度均小于 254B
![](https://cdn.xiaolincoding.com//mysql/other/462c6a65531667f2bcf420953b0aded9.png)

- 现在插入一个新的表头节点，且其`长度 > 254B`
![](https://cdn.xiaolincoding.com//mysql/other/d1a6deff4672580609c99a5b06bf3429.png)

- 触发连锁更新
![](https://cdn.xiaolincoding.com//mysql/other/1f0e5ae7ab749078cadda5ba0ed98eac.png)

</br>

#### 缺陷
由于「连锁更新」的存在，所以压缩列表只会用于**保存的节点数量不多**的场景

### 哈希表

#### 数据结构
dictht--哈希表结构
dictEntry--哈希表节点结构
![](https://cdn.xiaolincoding.com//mysql/other/dc495ffeaa3c3d8cb2e12129b3423118.png "Redis哈希表数据结构")
> `dictEntry **table`：哈希表数组，其中每个元素是指向哈希表节点的指针
> dictEntry中`next`指针指向下一个节点，以此实现**链式哈希**解决哈希冲突
> dictEntry中`联合体 v`存储实际数据，可以是**指向实际值的指针**，或是 **可以直接赋值的int、double**

#### rehash
Redis在实际使用哈希表时，定义了一个`dict`结构体，内部属性为两个哈希表
![](https://cdn.xiaolincoding.com//mysql/other/2fedbc9cd4cb7236c302d695686dd478.png "Redis哈希表实际使用结构")

</br>

- rehash过程
![](https://cdn.xiaolincoding.com//mysql/other/cabce0ce7e320bc9d9b5bde947b6811b.png "rehash过程")

1. 触发条件
> - **负载因子**(load factor) = 哈希表已保存节点数量 / 哈希表大小
> - 哈希表大小是指所有不同键的数量，但是由于哈希冲突的存在，所以节点数量 >= 哈希表大小
> - 当`负载因子>=1`,且没有执行`bgsave(RDB快照)`、`bgrewiteaof(AOF重写)`命令，进行 rehash
> - 当`负载因子>=5`,无论如何都 rehash

2. 渐进式rehash
- 为了避免 rehash 在数据迁移过程中，因拷贝数据的耗时，影响 Redis 性能
- 把一次性大量数据迁移工作的开销，分摊到了多次处理请求的过程中
- 具体过程
> - 正常服务请求阶段，插入的数据写入 `哈希表1`，`哈希表2`未分配空间
> - 当数据量增加，触发rehash后，为`哈希表2`分配空间（一般是表1的两倍）
> - 在rehash期间，每次对哈希表元素CRUD时，除执行相应操作（在两张表中都进行）之外，顺序地将 表1 中的key-value**迁移（表1中无，表2中有）**到 表2
> - 对于C R U D，C会直接放入表2；R会先查表1，若无，则查表2；
> - 最终 表1 会变成空表

### 整数集合

#### 数据结构
```
typedef struct intset {
    //编码方式
    uint32_t encoding;
    //集合包含的元素数量
    uint32_t length;
    //保存元素的数组
    int8_t contents[];
} intset;
```
> - 若 encoding = INTSET_ENC_INT16，则 contents 中每一个元素类型为 int16_t；
> - 若 encoding = INTSET_ENC_INT32，则 contents 中每一个元素类型为 int32_t；
> - 若 encoding = INTSET_ENC_INT64，则 contents 中每一个元素类型为 int32_t；

</br>

#### 升级（但没有降级）
当向整数集合加入新元素时，若新元素类型比已有元素类型都长时，需要按新元素类型扩展`contents`空间大小

- 实例
原本有三个`int_16`元素，现在要加一个`int_32`元素
1. 先扩容
![](https://cdn.xiaolincoding.com//mysql/other/e2e3e19fc934e70563fbdfde2af39a2b.png)

</br>

2. 再转换原本元素的类型（从后向前），并保持原本顺序
![](https://cdn.xiaolincoding.com//mysql/other/e84b052381e240eeb8cc97d6b729968b.png)