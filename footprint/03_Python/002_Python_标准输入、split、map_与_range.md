# Python 标准输入、split、map 与 range

> 学习层级：入门  
> 前置知识：[Python 环境与解释器](001_Conda、pip、Python_路径与包导入.md)  
> 后续阅读：[可变默认参数、容器修改与复制语义](003_可变默认参数、容器修改与复制语义.md)

## 1. `sys.stdin` 是可迭代文本流

命令行程序可以逐行读取标准输入：

```python
import sys

for line in sys.stdin:
    print(repr(line))
```

输入：

```text
10 20
30 40
```

通常会依次得到 `"10 20\n"` 和 `"30 40\n"`。但文件最后一行可能没有换行符，不能假定每行都以 `\n` 结尾。循环在 EOF 到来时结束。

手动输入 EOF 的常见方式：

- Windows 控制台：`Ctrl+Z` 后回车；
- Linux/macOS 终端：`Ctrl+D`。

## 2. `split(" ")` 与 `split()` 不同

显式传入一个空格时，只按该字符切分：

```python
line = "10   20\n"
print(line.split(" "))
# ['10', '', '', '20\n']
```

连续空格会产生空字符串，其他空白字符也不会被当作分隔符。

不传参数时，`str.split()` 按连续空白切分并忽略首尾空白：

```python
line = "  10\t20\n"
print(line.split())
# ['10', '20']
```

因此，算法题和一般命令行数字输入通常使用 `split()`。如果输入协议需要保留空字段，或只允许某一种分隔符，则应按协议显式选择分隔方式。

## 3. 解包与整数转换

解包要求右侧元素数量完全匹配：

```python
a, b = ["10", "20"]        # 正常
a, b = ["10"]              # ValueError: not enough values to unpack
a, b = ["10", "20", "30"]  # ValueError: too many values to unpack
```

`split()` 得到的仍是字符串。数值计算前需要转换：

```python
a, b = map(int, line.split())
print(a + b)
```

`map(int, nums)` 在迭代时对每个元素调用 `int`。Python 3 的 `map` 是惰性迭代器，不是列表：

```python
nums = ["10", "20", "30"]
converted = map(int, nums)
print(type(converted))
# <class 'map'>

values = list(converted)
# [10, 20, 30]
```

等价的列表推导式为：

```python
values = [int(item) for item in nums]
```

惰性也意味着转换错误通常在消费到坏值时发生，而不是在创建 `map` 时发生：

```python
values = list(map(int, ["10", "abc", "30"]))
# ValueError: invalid literal for int() with base 10: 'abc'
```

## 4. 常见输入模式

每行必须恰好有两个整数：

```python
import sys

for line_no, line in enumerate(sys.stdin, start=1):
    if not line.strip():
        continue

    try:
        a, b = map(int, line.split())
    except ValueError as exc:
        raise ValueError(f"第 {line_no} 行必须恰好包含两个整数") from exc

    print(a + b)
```

每行可以有任意数量的整数：

```python
import sys

for line in sys.stdin:
    nums = list(map(int, line.split()))
    print(nums)
```

第二种写法遇到空白行会得到 `[]`，本身不会报错；是否跳过空白行取决于输入协议。

## 5. `range(start, stop, step)` 的半开区间

`range` 包含 `start`，不包含 `stop`：

```python
list(range(2, 6))
# [2, 3, 4, 5]
```

步长不能为 0：

```python
range(1, 5, 0)
# ValueError: range() arg 3 must not be zero
```

当 `x >= 0` 时：

```python
list(range(x, -1, -1))
```

会从 `x` 倒序遍历到 `0`：

```python
list(range(5, -1, -1))
# [5, 4, 3, 2, 1, 0]

list(range(5, 0, -1))
# [5, 4, 3, 2, 1]
```

该结论必须带上 `x >= 0` 的条件，因为负步长要求起点大于停止值：

```python
list(range(-1, -1, -1))  # []
list(range(-2, -1, -1))  # []
```

## 6. `range` 不会预先创建整数列表

`range` 是紧凑的不可变序列对象，只保存起点、终点、步长等参数，并按需计算元素：

```python
r = range(1_000_000_000)
print(type(r))
# <class 'range'>
```

只有显式执行 `list(r)` 才会尝试物化所有元素，并产生相应内存开销。

## 7. 常见误区

- `sys.stdin` 的每一行一定带 `\n`；
- `split(" ")` 和 `split()` 完全相同；
- `map` 直接返回列表；
- `int()` 的转换失败一定发生在创建 `map` 时；
- 空白行执行 `list(map(int, line.split()))` 会报错；
- `range(x, -1, -1)` 对任意 `x` 都包含 0；
- `range` 会立即创建全部整数。

## 8. 参考资料

- [Python `sys.stdin` 文档](https://docs.python.org/3/library/sys.html#sys.stdin)
- [Python `str.split` 文档](https://docs.python.org/3/library/stdtypes.html#str.split)
- [Python `map` 文档](https://docs.python.org/3/library/functions.html#map)
- [Python `range` 文档](https://docs.python.org/3/library/stdtypes.html#ranges)
- 原始整理来源：[技术问题解答准则分享对话](https://chatgpt.com/share/6a69fbe0-2524-83ec-b330-b1326ce3d368)

