---
以小林coding图解redis为主脉，附加各种延伸内容；
感谢小林coding，感谢代码随想录，感谢知乎，感谢各种社区和论坛；
---
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


|              |                           SQL                           |                 NoSQL                 |
| :----------: | :------------------------------------------------------: | :------------------------------------: |
| 数据存储结构 |                    有固定行、列的表格                    |           文档、键值对、图等           |
|  数据关联性  |                       表与表可关联                       |            关联需要人为维护            |
|   数据查询   |                 使用统一SQL语句进行查询                 |             无固定查询语法             |
|     事务     | 支持事务，且必须满足ACID(原子性、一致性、隔离性、持久性) | 或不支持事务、或只需要BASE(最终一致性) |
| 数据存储位置 |                           磁盘                           |                  内存                  |
|    扩展性    |                           垂直                           |                  水平                  |

</br>

## Redis特征

1. 键值型，值支持多种不同数据结构
2. 单线程处理命令，每个命令具备原子性
3. 低延迟、速度快 (基于内存、IO多路复用、良好的编码)
4. 支持数据持久化
5. 支持主从集群、分片集群

</br>

## Redis通用命令

**官方说明文档：https://redis.ac.cn/docs/latest/commands/**

常见：

1. KEYS 查看符合模板的所有key，
   由于支持模糊匹配，所以当数据量到达一定规模，效率会很低，因此不建议在生产环境设备上使用

- 语法 `KEYS pattern`
- patterns支持模糊匹配

> `?`表示任意单字符；`*`表示若干个任意字符；`^`表示非；`[]`表示框中的某个字符；`a-k`表示从a到k中任意的某个字符
> `h？llo` 与 hello、hallo 和 hxllo 匹配
> `h*llo` 匹配 hllo 和 heeeello
> `h[ae]llo` 匹配 hello 和 hallo 但不匹配 hillo
> `h[^e]llo` 匹配 hallo、hbllo...但不是hello
> `h[a-b]Llo` 匹配 hallo  和 hbllo
> 如果想逐字匹配特殊字符，可以用 `\` 。

2. DEL 删除指定的一个key

- 语法 `DEL key [key ...]`
  可接受多个key
- 返回值：整数，被删除的**实际**键数量

3. EXISTS 判断key是否存在

- 语法 `EXISTS key [key ...]`
  可接受多个key
- 返回值：整型。参数中指定的`存在的`键的数量

4. EXPIRE 为 key 设置超时时间。超时时间到期后，该 key 将被自动删除
   具有关联超时的 key 通常被称为 易失的 (volatile)

- 语法 `EXPIRE key seconds [NX | XX | GT | LT]`

> NX -- 仅当 key 不存在超时时间时才设置超时
> XX -- 仅当 key 存在超时时间时才设置超时
> GT -- 仅当新的超时时间大于当前超时时间时才设置
> LT -- 仅当新的超时时间小于当前超时时间时才设置

5. TTL 返回具有超时的键的剩余生存时间

- 语法 `TTL key`
- 返回值

> 整数回复：TTL（以秒为单位）。
> 整数回复：如果键存在但没有关联的过期时间，则返回 -1。
> 整数回复：如果键不存在，则返回 -2。

</br>

## Redis数据类型

Redis是key-value型数据库，key一般是`String`类型，value类型则不固定

- key允许由多个单词形成层级结构，单词之间用`:`隔开

> 例如： 公司:项目:组:成员


|   类型   |         例子         |
| :-------: | :-------------------: |
| 基本类型 |                      |
|  String  |      hello world      |
|   Hash   | {a:"hello",b:"world"} |
|   List   |     [a->b->c->d]     |
|    Set    |      {A < B < C}      |
| SortedSet |   {A:1, B:2 , C:3}   |
| 特殊类型 |                      |
|    GEO    |     {A:(123,456)}     |
|  BitMap  |     0101011010010     |
| HyperLog |     0101011010010     |

</br>

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

</br>

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

</br>

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

</br>

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

</br>

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

</br>

### BitMap

</br>

### HyperLog

</br>

### GEO

</br>

### Stream

</br>

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

</br>

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
>
> 1. `newlen < 1 MB` -- 则SDS扩容至 `2*newlen`
> 2. `newlen >= 1 MB` -- 则SDS扩容至 `newlen + 1 MB`
>
> - 否则，直接使用剩余空间

#### 节省内存空间

- SDS五种类型：sdshdr5、sdshdr8、sdshdr16、sdshdr32、sdshdr64
- 不同类型的`len`、`alloc`数据类型不同，可以灵活存储不同大小的字符串
- Redis使用专门的编译优化来节省内存空间,
  告诉编译器取消结构体在编译过程中的优化对齐，按照**实际占用字节数**进行对齐

> - 在 `struct声明` 加上 **__attribute__ ((packed))**
>
>> 例如 struct __attribute__((packed)) test2{
>> $~~~~~~~~~~$ char a;
>> $~~~~~~~~~~$ int b;
>> }test2;
>> 默认情况下分配空间时，会进行字节对齐
>> ![](https://cdn.xiaolincoding.com//mysql/other/35820959e8cf4376391c427ed7f81495.png)
>> 而编译优化后，则不会浪费中间3个字节
>> ![](https://cdn.xiaolincoding.com//mysql/other/47e6c8fbc17fd6c89bdfcb5eedaaacff.png)
>>

</br>

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

</br>

### 压缩列表

内存紧凑型、占用一块**连续的**内存空间 --> 可以利用CPU缓存、对针对不同长度的数据进行相应编码

#### 结构设计

![](https://cdn.xiaolincoding.com//mysql/other/a3b1f6235cf0587115b21312fe60289c.png "Redis压缩列表及其节点数据结构")

> - 由**连续内存块**组成的**顺序型**数据结构
> - **压缩列表结构**
>
>> **zlbytes** -- 整个表占用的内存字节数
>> **zltail** -- 尾节点（entryN）距离起始地址的**偏移字节量**
>> **zllen** -- 表中节点数量
>> **zlend** -- 标记表的结束点，固定值 `0xFF(255)`
>>
>
> - **压缩列表节点**
>
>> **prevlen** -- `前一个节点长度`，方便实现从后向前遍历
>> $~~~~$若 前一节点长度小于**254B** ，则prevlen占用`1B`
>> $~~~~$否则，则prevlen占用`5B`
>> **encoding** -- 当前节点`实际数据`的`类型`、`长度`，主要为 字符串、整数
>> **data** -- 当前节点`实际数据`
>>

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

- 示例
  原本有三个`int_16`元素，现在要加一个`int_32`元素

1. 先扩容
   ![](https://cdn.xiaolincoding.com//mysql/other/e2e3e19fc934e70563fbdfde2af39a2b.png)

</br>

2. 再转换原本元素的类型（从后向前），并保持原本顺序
   ![](https://cdn.xiaolincoding.com//mysql/other/e84b052381e240eeb8cc97d6b729968b.png)

### 跳表

多层次有序链表，避免普通链表逐一查找的低效

#### 数据结构

- 跳表节点

```
typedef struct zskiplistNode {
    //Zset 对象的元素值
    sds ele;
    //元素权重值
    double score;
    //后向指针，指向前一个节点
    struct zskiplistNode *backward;

    //节点的level数组，保存每层上的前向指针和跨度,以此实现分层
    struct zskiplistLevel {
        //同层次的下一个节点
        struct zskiplistNode *forward;
        //跨度，记录两个节点间的距离
        unsigned long span;
    } level[];
} zskiplistNode;
```

![](https://cdn.xiaolincoding.com/gh/xiaolincoder/redis/%E6%95%B0%E6%8D%AE%E7%B1%BB%E5%9E%8B/3%E5%B1%82%E8%B7%B3%E8%A1%A8-%E8%B7%A8%E5%BA%A6.png)

</br>

- 跳表

```
typedef struct zskiplist {
    //头节点、尾节点指针
    struct zskiplistNode *header, *tail;
    //跳表长度
    unsigned long length;
    //最大层数
    int level;
} zskiplist;
```

#### 查询过程

1. 从头节点最高层开始，遍历每一层；
2. 对每个节点通过`元素值`和`权重值`进行比较

> 若**当前节点权重 < 要查找的权重**，访问该层的下一个节点；
> 若 **当前节点权重 == 要查找的权重 && 当前节点元素值 < 要查找的元素值**，访问该层的下一个节点；
> 否则，通过该节点**level数组**访问下一层，继续遍历

</br>

此过程类似递归，比如：
在下图所示跳表中查询 「元素：abcd，权重：4」

![](https://cdn.xiaolincoding.com/gh/xiaolincoder/redis/%E6%95%B0%E6%8D%AE%E7%B1%BB%E5%9E%8B/3%E5%B1%82%E8%B7%B3%E8%A1%A8-%E8%B7%A8%E5%BA%A6.drawio.png "跳表查询示例")
**当发现需要查找的元素在该层的两个相邻节点之间时，将跳转到下一层链表中进行搜索**

- 从头节点最高层2层开始，先找到 `节点A「元素：abc，权重：3」`，不匹配，访问 `A的2层指针`，指针为空，用 `A的1层指针`访问下层的下一节点；
- A的1层指针访问 `节点B「元素：abcde，权重：4」`，不匹配，访问 `B的1层指针`，指针为空，用 `B的0层指针`访问下层的下一节点;
- B的0层指针为空，返回到`访问B节点的上一个节点`,即 A，通过`A的0层指针`访问`节点C「元素：abcd，权重：4」`

</br>

#### 层数设置

- 跳表的相邻两层的节点数量最理想的比例是 2:1（下2上1），查找复杂度可以降低到 O(logN)
- 跳表在创建节点时，会在[0,1]生成一个随机数p

> 若 `p < 0.25`，层数+1，生成下一个随机数；
> `p > 0.25`，结束

- 层高最大限制为`ZSKIPLIST_MAXLEVEL`，`头节点创建`时高度就为h

> ZSKIPLIST_MAXLEVEL：Redis 7.0 定义为 32；Redis 5.0 定义为 64；Redis 3.0 定义为 32；

#### 为什么不用 平衡树 而用 跳表

1. 从实现上看
   对于插入、删除操作来说，平衡树可能引发子树调整（如 b+树 的节点分裂、合并），而跳表只需要修改相邻节点的指针；
2. 从内存占用上看
   平衡树节点固定具有两个指针，而跳表的指针数量平均为`1/(1-p)`（p为上面roll点的分界值），一般而言，后者占用内存更少；
3. 从实际使用上看
   做**范围查找**时，当找到范围上限或者下限之后：平衡树还需要中序遍历寻找其他范围内的值，这并不容易实现；而跳表只需要对同层节点进行遍历；

</br>

### quicklist

- 本身是**双向链表**，表中每个元素是个**压缩链表**；
- 因为压缩列表元素越少或越小，连锁更新带来的影响就越小，从而提供了更好的访问性能 **==>** 通过控制每个链表节点中的压缩列表的大小或者元素个数，来规避连锁更新的问题。；

#### 数据结构

- 表

```
typedef struct quicklist {
     //quicklist的链表头
     quicklistNode *head;

     //quicklist的链表尾
     quicklistNode *tail;

     //所有压缩列表中的总元素个数
     unsigned long count;

     //quicklistNodes的个数
     unsigned long len;
     ...
}quicklist;
```

- 表节点

```
typedef struct quicklistNode {
    //前一个quicklistNode
    struct quicklistNode *prev;

    //下一个quicklistNode
    truct quicklistNode *next;

    //quicklistNode指向的压缩列表
    unsigned char *zl; 

    //压缩列表的的字节大小
    unsigned int sz;   

    //压缩列表的元素个数
    unsigned int count : 16; 
    ···
} quicklistNode;
```

![](https://cdn.xiaolincoding.com//mysql/other/f46cbe347f65ded522f1cc3fd8dba549.png "quicklist数据结构")

> 当添加元素时，首先检查插入位置的节点压缩列表是否能放得下，若放不下，才创建新quicklistNode

</br>

### listpack

**每个节点不再包含前一个节点的长度** ==> 避免[连锁更新]，替代压缩列表

#### 数据结构

![](https://cdn.xiaolincoding.com//mysql/other/c5fb0a602d4caaca37ff0357f05b0abf.png "listpack数据结构")

- **encoding** 元素的编码类型，针对不同长度的整数和字符串
- **data** 实际存放的数据
- **len** encoding+data的总长度

</br>

## Reids线程模型

### 单线程（Redis4.0之前）

`网络IO`、`键值对读写`由**单一线程**完成，在主线程**顺序串行**完成各条命令请求；

一条命令的 `读`$\longrightarrow$`解析`$\longrightarrow$`执行`$\longrightarrow$`写` 都由唯一线程完成；

### “多”线程

1. Redis作为内存数据库，CRUD的执行非常快，性能瓶颈更多是在网络IO上；
2. **核心命令执行模块是单线程的**，即处理客户端的 GET、SET、HGET 等数据操作命令时，始终只有一个线程在工作；

   > - 避免传统多线程的上下文切换浪费资源；
   > - 避免传统多线程锁的竞争；
   >
3. Redis4.0引入`UNLINK`命令，由后台线程异步执行删除操作；
4. Redis6.0引入多线程IO，IO线程负责**读网络$\rightarrow$接收客户端命令**、**写网络$\rightarrow$返回结果**（也就是命令的`读`、`写`由IO线程完成，但命令的解析和执行依然由主线程完成）；
5. 需结合事件机制中的文件事件

</br>

## Redis事件机制

### 文件事件

- Redis基于Reactor模式开发的网络事件处理器-->文件事件处理器；

> 1. 使用IO多路复用，同时监听多个socket套接字，并为每个socket关联不同的事件处理函数；
> 2. 当socket的可读、可写事件触发，调用相应的事件处理函数；

- 文件事件处理器
  **套接字** +**IO多路复用程序** + **文件事件分派器** + **事件处理器**

![](https://pdai.tech/images/db/redis/db-redis-event-3.png "Redis文件时间处理器示意图")

> - 文件事件对应socket操作，每当一个socket准别好执行 `accept`、`read`、`write`、`close`等操作时，产生一个对应的文件事件；
> - IO多路复用程序监听Redis连接的多个socket，并向文件事件分派器传递产生事件的套接字；
> - 并发产生的多个文件事件会被IO多路复用程序放入同一队列（aeEventLoop的fired就绪事件表）中；
> - 事件处理器以**按序**、**同步**、**每次单个套接字**的方式处理就绪的文件事件。

![](https://pdai.tech/images/db/redis/db-redis-event-0.jpg "Redis多路复用IO模型")

示例：Redis客户端与服务器进行连接过程

> 1. 客户端向服务器发起连接请求，服务器端负责监听连接的socket产生**AE_READABLE**事件，触发连接应答处理器进行应答；
> 2. 服务器端创建一个新的**客户端套接字**、**客户端状态**，并将该套接字的AE_RAEDABLE事件与命令请求处理器关联；
> 3. 建立连接后，客户端向服务器发送命令，相应的客户端套接字产生AE_READABLE事件，触发命令请求处理器，读取客户端命令，并调用相关程序进行执行；
> 4. 服务器执行命令后得到想要相应的**命令回复**，将客户端套接字的**AE_WRITEABLE**事件与**命令回复处理器**进行绑定，当对应的客户端套接字的发送缓冲区空间可用时，AE_WRITEABLE事件触发，命令回复处理器进行相关处理，将命令回复写入发送缓冲区；
> 5. 若命令回复数据全部发送完成，删除AE_WRITEABLE事件与命令回复处理器的绑定；否则，保留。

</br>

### 时间事件

- 分类：

  1. 定时事件：相应程序在指定时间执行一次；
  2. 周期性事件：相应程序每隔固定时间执行一次；
  3. 区别：时间处理器返回值

     > - **AE_NOMORE**：定时事件，到设定时间后触发时间处理器执行一次相应程序，之后**删除**该事件；
     > - **其他值**：周期性事件，事件到达后触发处理器执行相应程序，之后修改该事件的**when**属性值，让该事件能再次达到；
     >
- 时间事件源码定义：

  ```
  typedef struct aeTimeEvent {
      /* 全局唯一ID */
      long long id; /* time event identifier. */
      /* 精确到秒的UNIX时间戳，记录时间事件到达的时间*/
      long when_sec; /* seconds */
      /* 精确到毫秒的UNIX时间戳，记录时间事件到达的时间*/
      long when_ms; /* milliseconds */
      /* 时间处理器 */
      aeTimeProc *timeProc;
      /* 事件结束回调函数，析构一些资源*/
      aeEventFinalizerProc *finalizerProc;
      /* 私有数据 */
      void *clientData;
      /* 前驱节点 */
      struct aeTimeEvent *prev;
      /* 后继节点 */
      struct aeTimeEvent *next;
  } aeTimeEvent;
  ```
- Redis主要的时间事件

  1. 核心周期性时间事件serverCron：

     > - 周期性时间事件；
     > - Redis 服务器的"心跳"，处理各种维护任务，如`更新LRU时钟`、`更新服务器每秒执行命令的次数`、`处理SIGTERM信号`、`执行被延迟的BGREWRITEAOF`等；
     > - **默认频率**：每秒执行 **server.hz** 次（默认 `hz=10`）
     >
  2. 模块定时器处理器moduleTimerHandler

</br>

## “多”线程与事件机制结合梳理

### IO多路复用

[IO多路复用——深入浅出理解select、poll、epoll的实现 - 知乎](https://zhuanlan.zhihu.com/p/367591714)

epoll：[从青铜到王者：带你吃透epoll核心机制-51CTO.COM](https://server.51cto.com/article/814165.html)

### 以epoll为例过程

![](https://pic1.zhimg.com/v2-97e9acf83e6dbd659fdbfed9a914ae86_1440w.jpg)

- aeEventLoop在且只在主线程中；
- 图中的未就绪文件事件表描述不准确，应为**注册文件事件表**，存储所有**已注册**的事件的相关信息，比如：读事件or写事件、回调函数指针等；q其中元素定义如下：

  ```
  typedef struct aeFileEvent {
      int mask;                 // AE_READABLE | AE_WRITABLE
      aeFileProc *rfileProc;    // 读事件回调
      aeFileProc *wfileProc;    // 写事件回调
      void *clientData;         // client 指针
  } aeFileEvent;
  ```

1. 主线程事件循环

   ```
   while (!server.shutdown) {
       aeProcessEvents(eventLoop);
   }

   aeProcessEvents():
   1. aeApiPoll()           // epoll_wait
   2. processFileEvents()  // 处理 fired 事件
   3. processTimeEvents()  // 时间事件
   4. processIOThreads()或handleClientsWithPendingReadsUsingThreads()   // ★ Redis 6+ 新增阶段，接管IO线程处理结果
   ```
2. aeApiPoll()：主线程调用`epoll_wait`，系统内核从epoll红黑树中找到所有就绪事件，放入epoll就绪事件表；
3. 主线程从epoll就绪事件表中将上一步得到的就绪事件，经过一定转换（如 `fired[0] = { fd=5, mask=AE_READABLE }`），放入aeEventLoop.fired；
4. processFileEvents()：主线程遍历aeEventLoop.fired，对每个就绪事件从aeEventLoop.events中找到相应的**回调函数**；
5. processTimeEvents()：时间事件处理类似；
6. 在回调函数中，主线程会将需要分配出去的IO操作分配给对应的IO线程（有些回调，比如接受新连接，主线程自己就能搞定，不需要交给IO线程）；
7. processIOThreads()：

   - 读：IO线程执行`read()`将socket发来的命令读入对应请求的`client对象`的`querybuf`中，主线程执行`processInputBuffer()`，读出命令并解析、执行；
   - 写：主线程执行命令的过程中把结果写入对应请求的`client对象`的`replybuf`，IO线程执行`write()`，将缓冲区的内容通过socket发送给客户端；对于写命令来说，这一阶段主线程是要回收write()的执行结果，并决定是否继续监听`AE_WRITABLE`(可能结果比较大，一次写不完)；

## Redis持久化

两种持久化技术：**AOF日志** 、**RDB快照**

### AOF日志（Append Only File）

Redis每执行一条**写操作命令**，便将该命令追加到一个特定文件（AOF日志文件）中，**重启Redis时**读取并执行，达到恢复缓存数据的效果
![](https://cdn.xiaolincoding.com//mysql/other/6f0ab40396b7fc2c15e6f4487d3a0ad7.png "AOF下发起写命令")

- 先执行写操作，在将命令写入AOF日志
- - 避免额外的检查开销

> 能执行说明该命令没问题。省的到时候把命令读出来还要检查语法等正确性

- - 不会阻塞当前写命令的执行

> 先执行命令再记录，保证写命令执行优先

示例：
![](https://cdn.xiaolincoding.com//mysql/other/337021a153944fd0f964ca834e34d0f2.png "命令示例")

AOF日志文件中存**文本**

- `*n`：表示目录中有`n`个部分
- `$l`：表示该部分的字节长度为`l`
- `set`：该部分的具体内容

</br>

#### 风险

1. 丢失

> 执行完写命令，在将该命令写入磁盘时，出现诸如服务器宕机等情况时，会造成数据丢失；

2. 可能阻塞下一条命令

> 写命令的执行 和 写命令写入AOF日志文件 都是在主进程进行的；如果写入磁盘的效率太低，会阻塞后续命令执行
> ![](https://cdn.xiaolincoding.com//mysql/other/28afd536c57a46447ddab0a2062abe84.png)

#### 写回策略 （when写入硬盘）

![](https://cdn.xiaolincoding.com//mysql/other/4eeef4dd1bedd2ffe0b84d4eaa0dbdea.png "AOF日志写入过程")

> 内核指操作系统内核

#### 底层实现

- 本质上是改变调用函数`fsync()`的时机；
- fsync() 是一个用于强制将文件数据和元数据从内核页缓存写入磁盘的系统调用函数；调用会阻塞，直到底层存储设备报告写入完成。

##### Always -- 牺牲性能->减少数据丢失

每次执行完写操作，同步将AOF日志数据写入硬盘（上图流程一次性走完）

##### Everysec -- 折中

每次执行完写操作，先将命令写入**AOF缓冲区（AOF文件的内核缓冲区）**，之后**每隔一秒**将缓存中数据写入硬盘

##### No -- 数据丢失不可控->提升性能

每次执行完写操作，先将命令写入**AOF缓冲区**，之后何时写入硬盘由操作系统来决定，Redis开摆不管

#### 重写机制 （避免AOF日志文件过大）

- 当AOF日志文件大小超过设定阈值，创建一个子进程启动AOF重写机制来压缩文件
- 重写时，读取数据库中**所有键值对**，将每一对用一条命令记录到**新·AOF日志文件**中，记录完成后替代掉原本的AOF日志文件

示例：

> 1. 先执行**set name A**
> 2. 再执行**set name B**
> 3. 则此时，原本的AOF日志文件中就会有两条写指令；但是实际的键值对只有**name:B**
> 4. 所以采用重写，新的AOF日志文件中只会有一条**set name B**，达到了缩小AOF日志文件的效果

- Why 创建新文件 instead 复用（直接修改）原本文件 ?

> 避免重写过程中出现意外导致原本的AOF日志文件失效
> 示例：

```
//假设现有 AOF 文件内容（完整）：
SET key1 value1
SET key2 value2
SET key3 value3
...
//（共 1000 行）
//开始重写，直接覆盖这个文件：
//写入新内容：
SET key1 new_value1   //← 写完这一行后崩溃！
//（文件到此中断）
```

> 则此时 旧内容被破坏（已覆盖）、新内容不完整 --> Redis 重启时无法加载这个损坏的 AOF 文件

#### 后台重写

避免AOF重写在主进程执行

- AOF重写由后台子进程`bgrewriteaof`执行

> - 子进程重写，主进程可以继续处理命令请求，避免阻塞
> - 采用进程而非线程，且子进程保存主进程的**数据副本**
> - - 若采用线程，则线程间共享内存，修改这部分数据时需要通过加锁来保证数据安全，此举会降低性能
> - - 采用进程，虽然父子进程也共享内存，但是这部分数据是**只读**的，当父/子进程需要**修改或写入**共享内存中的数据时，会**写时拷贝**，即系统为该进程分配新的物理并复制**需要修改数据**到此内存，因此父子进程会拥有独立的数据副本，无需加锁

##### 创建进程 共享内存、写时拷贝

![](https://cdn.xiaolincoding.com//mysql/other/5a1f2a90b5f3821c19bea3b7a5f27fa1.png "父子进程共享内存")
![](https://cdn.xiaolincoding.com//mysql/other/d4cfac545377b54dd035c775603b4936.png "写时拷贝")
when**父进程阻塞**：

1. 为子进程复制页表
2. 写时拷贝复制内存数据

但这会导致两个问题：

> - 当主进程需要修改一个数据量比较大键值对，那么写是拷贝需要跨比较多的时间，可能会导致主进程阻塞
> - 写时拷贝为主进程分配新内存空间，那子进程进行重写读到的数据就不是最新的了，这就违背了AOF持久化的初衷。

因此，引入AOF重写缓冲区来解决这个问题

##### AOF重写缓冲区

在创建`bgrewriteaof子进程`后使用

![](https://cdn.xiaolincoding.com//mysql/other/watermark,type_ZmFuZ3poZW5naGVpdGk,shadow_10,text_aHR0cHM6Ly9ibG9nLmNzZG4ubmV0L3FxXzM0ODI3Njc0,size_16,color_FFFFFF,t_70-20230309231944807.png "AOF重写缓冲区工作示意图")

- 当主进程需要执行一个写命令：
- - 执行此命令（先）
- - 将此命令写入**AOF缓冲区**
- - 将此命令写入**AOF重写缓冲区**
    </br>
- 当子进程完成重写，向主进程发送一个异步信号
  </br>
- 主进程收到该信号后，调用信号处理函数：
- - 将 [AOF重写缓冲区] 内容**追加**到**新·AOF文件**
- - 对新AOF文件改名，覆盖原AOF文件

</br>

### RDB快照

记录某一时刻内存的实际数据（**全量快照**，即记录内存中的**所有数据**），恢复数据直接将RDB文件读入内存，效率高于AOF；

RDB 文件的加载工作是在服务器启动时自动执行的

#### save & bgsave

##### save

在主线程生成RDB文件，属于IO操作，可能会阻塞主线程

##### bgsave

创建子进程来生成RDB文件，避免主线程阻塞

#### 保存快照与数据修改

与AOF日志类似，通过**写时复制**，在执行快照保存期间，主进程可以继续接受写命令请求并执行

</br>

### AOF与RDB结合(混合持久化)

- 4.0版本提出
- 既利用RDB恢复数据效率高，又利用AOF数据丢失少（RDB的保存频率难以控制，太快开销太大，太慢数据丢失）
- **AOF日志重写**过程中起作用

> - 在AOF重写时，子进程以**RDB形式**保存内存数据
> - 之后主线程执行的写命令**保存到AOF重写缓冲区之后**，以**AOF方式**将其写入新AOF文件
> - 因此，得到的AOF文件一部分是RDB格式的全量数据，一部分是AOF形式的写命令

</br>

## Redis过期删除策略

当对**key**设置过期时间，通过**过期删除策略**删除已过期的键值对

### 相关命令

- 对已有的key设置

1. `expire <key> <n>`：设置`key`在`n秒`后过期；
2. `pexpire <key> <n>`：设置`key`在`n毫秒`后过期；
3. `expireat <key> <n>`：设置`key`在某个时间戳(精确到`秒`)之后过期；
4. `pexpireat <key> <n>`：设置`key`在某个时间戳(精确到`毫秒`)之后过期；

</br>

- 定义key并设置

1. `set <key> <value> ex <n>`：`n秒`后过期；
2. `set <key> <value> px <n>`：`n毫秒`后过期；
3. `setex <key> <n> <value>`：`n秒`后过期；

</br>

- 查看key剩余存活时间
- `TTL <key>`

> 返回剩余**秒**数
> key不存在返回 **-2**
> 过期时间不存在返回 **-1**

</br>

- 取消key过期时间
- `PERSIST <key>`

</br>

### 判断key过期

当某个key被设置了过期时间，Redis会将该key存入**过期字典(expiresdict)**，该字典中键为指向key的指针，值为过期时间值的long long整型

</br>

### 过期删除策略

#### 定时删除

设置key的过期时间的同时创建一个**定时事件**，当到达过期时间时，**事件处理器**自动执行key的删除操作

- cpu占用但可以尽快释放内存

#### 惰性删除

**不主动删除**过期key，每次访问key的时候检测是否过期，若过期再删除

- 内存释放不及时但cpu占用少

#### 定期删除

每隔一段时间**随机**取出一定数量的key，检查并删除其中过期的key

- 折中</br>

</br>

## Redis内存淘汰

当Redis的运行内存达到所设置的最大运行内存（maxmemory B）时，触发内存淘汰策略;

> - 64位OS中，maxmemory默认值=0，表示没有内存大小限制；
> - 32位OS中，maxmemory默认值=3G，32位机器内存最大仅为4G，留1G给系统本身；

- `config get maxmemory-policy`命令查看当前Redis内存淘汰策略；
- `config set maxmemory-policy <policy>`命令暂时性修改当前Redis内存淘汰策略为`<policy>`，立即生效，重启失效；
- 修改Redis文件配置中`maxmemory-policy <policy>`，重启后生效，且一直有效；

### 不进行数据淘汰的策略

#### noeviction

Redis3.0后默认的内存淘汰策略；

当运行内存超过**最大设置内存**时，不淘汰任何数据；

若有新数据写入，报错**禁止写入**；

若只是查询或删除，无妨；

### 进行数据淘汰的策略

#### 淘汰范围==设置过期时间的数据

##### volatile-random

随机淘汰；

##### volatile-ttl

优先淘汰更早过期的；

##### volatile-lru（Redis3.0前默认）

淘汰最久未被使用的；

##### volatile-lfu（Redis4.0新增）

淘汰最不频繁被使用的；

#### 淘汰范围==所有数据

##### allkeys-random

随即淘汰；

##### allkeys-lru

淘汰最久未被使用的；

##### allkeys-lfu（Redis4.0新增）

淘汰最不频繁被使用的

### LRU vs LFU

Redis对象部分定义：

```Redis对象部分结构
typedef struct redisObjetct{
  ···
  //24位
  unsigned lru:24;
  ···
}
```

#### LRU

- 避免传统LRU实现的问题：

  > 1. 用**链表**管理所有的缓存数据 $\longrightarrow$ 空间开销；
  > 2. 数据被访问，需要将链表中对应的节点移动到表头$\longrightarrow$时间、性能开销；
  >
- Redis实现方式：

  > 1. 在对象结构体中**lru属性**记录**最后一次被访问的时间戳**；
  > 2. 淘汰时，**随机采样**，随机取若干值，淘汰其中**最久没被使用**的；
  >
- 问题：
  **缓存污染**：某些数据被访问次数很少，但在缓存中待的时间很久；

#### LFU

根据访问频率进行淘汰；

- Redis对象lru属性

  > 1. 高**16**位存储**ldt：访问key的时间戳**；
  > 2. 低**8**位存储**logc：key的被访问频次**，初始值=5，logc越小表示使用频率越低；
  >
- logc变化规则

  1. 当对应的key被访问是，会使用LFULogIncr()对logc的值进行更新；
  2. 进行淘汰时，会使用LFUDecrAndReturn()对淘汰范围内Redis对象的logc进行计算，从而淘汰logc最小的键值；

  > - logc的值会随时间推移而衰减，衰减的值取决于**前后两次访问的时间差**；
  > - 对应的key被访问时，还需要**按一定概率**对logc进行**增加**；
  > - **lfu-decay-time**：单位：分钟，默认为1，用于调整logc**衰减速度**；
  > - **lfu-log-factor**：用于调整logc**增长速度**；
  >

  ```
  // 更新LFU计数器的算法
  uint8_t LFULogIncr(uint8_t counter) {
      if (counter == 255) return 255;  // 达到最大值

      // 计算随机增加概率
      double r = (double)rand()/RAND_MAX;
      double baseval = counter - LFU_INIT_VAL;  // LFU_INIT_VAL=5
      if (baseval < 0) baseval = 0;

      // 概率公式：1/(衰减因子 * 计数器值 + 1)
      double p = 1.0/(baseval * server.lfu_log_factor + 1);

      if (r < p) counter++;  // 以概率p增加计数器

      return counter;
  }

  // 计算衰减后的计数器值
  unsigned long LFUDecrAndReturn(robj *o) {
      // 获取最后访问时间（高16位）
      unsigned long ldt = o->lru >> 8;
      // 获取当前计数器值（低8位）
      unsigned long counter = o->lru & 255;

      // 计算经过的分钟数
      unsigned long num_periods = server.lfu_decay_time ? 
          LFUTimeElapsed(ldt) / server.lfu_decay_time : 0;

      if (num_periods)
          counter = (num_periods > counter) ? 0 : counter - num_periods;
      return counter;
  }
  ```

  </br>

## 主从复制

为避免单Redis服务器故障而导致单点故障 $\longrightarrow$ 将数据备份到多个Redis服务器；

为保证多Redis服务器的数据一致性 $\longrightarrow$ [主从复制]；

主服务器**可读可写**，从服务器**一般只读** $\longrightarrow$ [读写分离]，写操作先在主服务器执行，之后由主服务器将写操作发给从服务器进行执行；

![](https://cdn.xiaolincoding.com//mysql/other/2b7231b6aabb9a9a2e2390ab3a280b2d-20230309232920063.png "主从复制、读写分离")

### 第一次同步

- `replicaof <服务器A的IP地址> <服务器A的Redis端口号>`
  从服务器B执行上述命令，成为服务器A的从服务器；

![](https://cdn.xiaolincoding.com//mysql/other/ea4f7e86baf2435af3999e5cd38b6a26.png "主从复制第一次同步过程示意图")

#### 阶段一：建立连接，协商同步

1. 从服务器执行`replicaof`后，给主服务器发`psync`命令，请求进行数据同步；

   > psync命令参数：
   >
   > 1. 主服务器runID：第一次同步时= **?** ，对应每个Redis服务器启动时生成的随机ID，第一次同步时不知道主服务器ID，因此     为“?”；
   > 2. 复制进度offset：第一次同步时= **-1**；
   >    主服务器、从服务器分别维护自己的复制进度（偏移量），单位：字节，若两者相等则说明数据库状态一致；（具体的看后面）
   >
2. 主服务器收到psync命令后，发送`FULLRESYNC`命令响应从服务器，表示采用**全量复制**，从服务器收到后记录FULLRESYNC携带的参数；

   > FULLRESYNC命令参数：
   >
   > 1. 主服务器runID；
   > 2. 复制进度offset；
   >

#### 阶段二：主服务器同步数据给从服务器

1. 主服务器执行`bgsave`命令生成RDB文件（子进程），并将此文件异步发送给从服务器（主进程、事件机制）；
2. 从服务器收到RDB文件后，先清空当前数据，再载入RDB文件；
3. 由之前的知识可知，`bgsave`命令是启动子进程生成RDB文件，此时主进程并未阻塞，因此可以继续响应写命令 $\longrightarrow$ 执行bgsave命令之后的数据修改会导致主从服务器之间的数据不一致；
4. 为解决上述问题，主服务器在 **生成RDB文件期间**、**发送RDB文件期间**、**从服务器加载RDB文件期间** 将收到的写操作命令写入**replication buffer缓冲区**（每个从服务器对应一个）；（说白了，就是在 `执行bgsave命令 到 从服务器加载完RDB文件` 这段时间）

#### 阶段三：主服务器发送 新·写指令 给从服务器

1. 从服务器加载完主服务器发送的RDB文件之后，回复**确认消息**给主服务器；
2. 主服务器将**replication buffer**中的写操作命令发送给从服务器，从服务器收到后执行，完成第一次同步；

### 基于长连接的命令传播

- 第一次同步之后，主从服务器之间维持TCP连接；
- 主服务器通过此连接将后续写操作命令发给从服务器；
- TCP连接为**长连接**，避免短连接频繁连接、断开的性能开销；

### 主服务器压力分摊

#### 原本模式的问题

1. 由于 `fork()` 产生子进程会阻塞主进程，当主服务器有多个从服务器时，每进行一次主从复制的首次同步都需要执行一次 `fork()` 可能导致主服务器无法正常处理数据读写请求；
2. 传输RDB文件在主进程执行，会占用网络带宽；

#### 解决$\longrightarrow$从服务器分级

- 将一部分从服务器的同步交给另一部分层次更高的从服务器；
- 低层次从服务器执行`replicaof <高层次从服务器IP> 6379`成为高层次从服务器的从服务器；

![](https://cdn.xiaolincoding.com//mysql/other/4d850bfe8d712d3d67ff13e59b919452.png "分摊主服务器压力组织形式示意图")

### 增量复制

当主从服务器之间网络连接异常，致使数据同步不及时，导致客户端读从服务器中的旧数据；

连接恢复后：

1. Redis2.8之前：重新来一次主从复制；[开销太大]
2. Redis2.8及之后：将网络断开期间主服务器收到的写命令同步给从服务器$\longrightarrow$增量复制；

![](https://cdn.xiaolincoding.com//mysql/other/e081b470870daeb763062bb873a4477e.png "增量复制过程示意图")

#### 过程步骤

1. 从服务器发送`psync`命令给主服务器，参数`runID`、`offset`分别设为当前对应的值；
2. 主服务器收到后，以`CONTINUE`命令响应从服务器，表明采用增量同步；
3. 主服务器发送断连期间的写命令给从服务器，从服务器执行；

#### 增量感知

![](https://cdn.xiaolincoding.com//mysql/other/2db4831516b9a8b79f833cf0593c1f12.png "增量感知示意图")

##### repl_backlog_buffer

- **环形**缓冲区；
- 当主服务器进行**命令传播**时，除了发给从服务器，也会将写命令写入这个buffer（主服务器就这一个，和第一次同步中的replication buffer不一样）；

##### replication offset

- 标记`repl_backlog_buffer`的同步进度；
- **master_repl_offset**：主服务器标记自己 **[写]** 到哪；
- **slave_repl_offset**：从服务器标记自己 **[读]** 到哪；

##### HOW

- 主服务器收到从服务器重连之后的`psync`，根据命令中携带的`slave_repl_offset`与自身的`master_repl_offset`比较

> 1. 由于**repl_backlog_buffer**是环形的，若主服务器在buffer已满的情况下继续写入会覆盖原本的内容；
> 2. 两个offset以字节为单位，表示各自进度，如果二者的差值大于repl_backlog_buffer的大小，那么表示从服务器需要同步的数据不在其中，需要**全量同步**；否则**增量同步**。

- 当服务器写的速度远超从服务器读的速度，就会导致频繁全量同步 $\longrightarrow$ 尽可能怎大repl_backlog_buffer尺寸

  > 1. 标准：**second * write_size_per_second**;
  > 2. **second**：断连后，从服务器重连上主服务器的平均时间（秒）；
  > 3. **write_size_per_second**：主服务器平均每秒产生的写命令数据量大小；
  > 4. 通过修改配置文件中的 repl_backlog_buffer 参数值；
  >

</br>

## 哨兵（Sentinel）机制

Redis2.8及之后版本；

**主从节点故障转移**$\longrightarrow$检测主节点是否存活，若主节点挂了，选举一个从节点作为新的主节点，并通知其他从节点和客户端；

哨兵节点：运行在特殊模式下的Redis进程，通常与其他节点部署在同一台机器，减少资源开销，主要负责**监控**、**选主**、**通知**；

### 监控

#### 过程

1. 哨兵每隔一段时间（1s）给所有主从节点发送**PING**命令；
2. 主从节点收到后，发送**响应命令**给哨兵；
3. 若某个节点未在规定时间（配置项down-after-milliseconds）内响应，哨兵将其标记为[**主观下线**]；

#### 客观下线

![](https://cdn.xiaolincoding.com//picgo/d0bed80d28a543fd8dcd299d4b06cf04.png)

- 只针对主节点；
- 主节点可能因为响应压力大或网络阻塞等问题未能在规定时间内响应PING命令；
- 为了减少对主节点的下线误判$\longrightarrow$部署多个哨兵节点$\longrightarrow$**哨兵集群**（最少三个哨兵节点，且尽量奇数）；

1. 当哨兵节点A判定主节点主观下线，会发送**sentinel is-master-down-by-addr**命令向其他监控此主节点的哨兵询问是否同意该主节点下线；

   > 1. sentinel is-master-down-by-addr \<ip> \<port> \<current_epoch>  \<runid>
   > 2. ip、port：询问对应ip地址、端口的redis进程是否下线；
   > 3. current\_epoch：当前纪元；
   > 4. runid：如果为`当前哨兵节点的runid`，则此命令用于申请自己成为故障处理的leader；如果是`*`，则此命令用于向其他哨兵节点确认master 是否下线；
   >
   > leader就是后面要选出来负责故障转移的哨兵节点；
   >
2. 其他哨兵收到后，检测主节点是否已下线，之后返回一条包含三个参数的回复；

   > 1. down\_state：该哨兵 节点对于主节点的下线判断，1是下线，0是在线；
   > 2. leader\_runid：当等于`*`时，代表返回结果是说明主节点是否不可达；当等于具体的runid，代表目标节点同意此runid的对应节点成为 leader；
   > 3. leader\_epoch：该哨兵节点的纪元值，仅在 leader\_runid 值不为 \* 时有效；
   >
3. 当哨兵节点A收到其他哨兵节点的回复，若赞同主节点下线的票数达到**配置项quorum**设定值后，主节点被标记为[**客观下线**]；

- quorum一般设定为**哨兵数量/2+1**

### 选主

#### 推选Leader

- epoch纪元：标记故障转移周期的逻辑时钟，初始=0，可以简单理解为**第几轮选举**；选举有时候并不是一次就能成功选出 leader 的，可能要经过多轮投票选举，才可能选出合适的 leader；

1. 当某个哨兵节点**检测到主节点客观下线**，就作为[候选人]发起选举，**epoch+1**，并向其他哨兵节点发送**sentinel is-master-down-by-addr**命令；
2. 每个哨兵节点在一个epoch中只能投一次票，通常会投给第一个给自己发sentinel is-master-down-by-addr命令的节点，除了[候选人]的哨兵节点不能投票给自己；
3. 候选人胜出必须：

   > 1. 得票半数以上；
   > 2. 得票数大于等于quorum值；
   >

#### 选新主节点
