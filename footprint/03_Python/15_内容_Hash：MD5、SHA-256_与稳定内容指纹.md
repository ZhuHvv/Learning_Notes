# 03.15 内容 Hash：MD5、SHA-256 与稳定内容指纹

## 1. 总体性概念

内容 Hash 是把任意长度的**字节序列**映射为固定长度摘要：

```text
digest = H(content_bytes)
```

摘要也常被称为 Hash 值或内容指纹。它不是加密：

```text
加密：明文 → 密文 → 持有密钥时可以解密
Hash：原文 → 摘要，通常不能从摘要还原原文
```

MD5 和 SHA-256 都是 Hash 算法。对 UTF-8 字节串 `b"hello"`：

```text
MD5:
5d41402abc4b2a76b9719d911017c592

SHA-256:
2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
```

## 2. 原理性解释

### 2.1 Hash 处理字节，不处理抽象的“语义”

只要输入字节完全一致，摘要就一致；字节有微小变化，摘要通常会明显变化：

```text
"hello"
"Hello"
"hello\n"
"hello "
```

这些文本的大小写、换行或尾随空格不同，Hash 也不同。输入只变化一点，摘要却显著变化的性质常称为**雪崩效应**。UTF-8 与 UTF-16 编码得到的字节不同，同一可见文本也会产生不同摘要。

因此，内容 Hash 判断的是“约定表示下的精确相同”，不是语义相似。语义去重仍需 Embedding、规则或模型判断。

### 2.2 输出长度固定

无论输入是几个字节还是几 GB 文件：

| 算法 | 摘要长度 | 十六进制长度 |
|---|---:|---:|
| MD5 | 128 bit | 32 字符 |
| SHA-256 | 256 bit | 64 字符 |

每个十六进制字符表示 4 bit，所以 `128 / 4 = 32`，`256 / 4 = 64`。

### 2.3 碰撞必然存在，但安全目标是难以构造

输入空间无限、摘要空间有限，理论上一定存在：

```text
content_a != content_b
H(content_a) == H(content_b)
```

这称为 Hash 碰撞。密码学 Hash 的目标不是让碰撞在数学上不存在，而是让攻击者难以找到或构造碰撞。

### 2.4 MD5 的安全边界

MD5 输出 128 bit 摘要，但其抗碰撞性已经失效。它可以用于攻击者不能控制输入的非安全场景，例如兼容协议、普通缓存键或弱文件指纹；不能用于：

- 数字签名、证书和可信内容身份；
- 防篡改校验与安全文件分发；
- 密码存储；
- 任何依赖抗碰撞性的安全边界。

“MD5 更短、更快”不能弥补安全属性缺失。即使只做完整性校验，只要攻击者可能恶意构造输入，也应使用满足安全要求的算法和认证机制。

### 2.5 SHA-256 的定位

SHA-256 属于 SHA-2 算法族，输出 256 bit 摘要。相较 MD5，它仍适合常规内容标识和密码学完整性场景，但裸 SHA-256 也不等于身份认证：

- 需要证明消息来自持有密钥的一方时，应使用 HMAC 等认证结构；
- 密码存储应使用带盐、计算成本可调的专用密码哈希方案，而不是直接 SHA-256；
- 算法安全不代表输入规范、传输来源和比较逻辑自动安全。

## 3. 机制流程

内容指纹的稳定性来自“先定义规范化规则，再计算字节摘要”：

```text
原始文本
  ↓ 明确是否允许换行、空白、Unicode 等规范化
规范化文本
  ↓ 固定字符编码，例如 UTF-8
稳定字节序列
  ↓ SHA-256
固定长度摘要
```

规范化不是越多越好。删除空白、改变 Unicode 形式或重新排序字段可能把业务上不同的内容合并。规则必须写进协议，并在写入端和读取端保持一致。

## 4. 类比理解

内容 Hash 像对一份文件的精确字节版本制作固定长度指纹。指纹相同可以高效提示“很可能是同一字节内容”，但它不会解释内容含义，也不会自动证明文件来自可信发送方。

## 5. 应用举例 / 代码或伪代码

### 5.1 Python `hashlib`

```python
import hashlib

content = "hello"
content_bytes = content.encode("utf-8")

md5_digest = hashlib.md5(content_bytes).hexdigest()
sha256_digest = hashlib.sha256(content_bytes).hexdigest()

print("MD5:", md5_digest)
print("SHA-256:", sha256_digest)
```

输出：

```text
MD5: 5d41402abc4b2a76b9719d911017c592
SHA-256: 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
```

`.digest()` 返回原始二进制摘要，`.hexdigest()` 返回便于存储和显示的十六进制字符串。两者表达同一摘要，不是两种不同算法。

### 5.2 RAG 文档入库前生成稳定内容 ID

```python
import hashlib


def normalize_text(text: str) -> str:
    # 这是业务约定，不是通用真理。
    return text.replace("\r\n", "\n").strip()


def content_hash(text: str) -> str:
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
```

此处 ID 的准确定义是：

```text
SHA256(规范化后的 UTF-8 字节)
```

它适合精确去重、幂等入库和变更检测，但不能识别“措辞不同、语义相同”的文档。

### 5.3 文件流式计算

大文件不需要一次性读入内存：

```python
import hashlib
from pathlib import Path


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while block := file.read(block_size):
            digest.update(block)
    return digest.hexdigest()
```

## 6. 你在讨论中的理解推进

- 起点：你询问内容 Hash、MD5 与 SHA-256 摘要分别是什么。
- 关键区分：摘要是字节序列的固定长度指纹，不是可逆加密，也不是语义相似度。
- 工程推进：计算前必须明确编码和规范化规则，否则肉眼相同或近似的文本仍可能产生不同摘要。
- 安全边界：MD5 的抗碰撞性已经失效；SHA-256 更稳妥，但密码存储、消息认证等场景仍需专用结构。

## 7. 常见误区与排查思路

- **误区：Hash 相同等于语义相同。** Hash 比较的是约定字节表示。
- **误区：Hash 是加密。** 摘要没有对应的解密过程。
- **误区：MD5 可用于可信防篡改。** 攻击者可控输入下不能依赖其抗碰撞性。
- **误区：文本一样，Hash 就一定一样。** 先检查编码、换行、BOM、Unicode 规范化和尾随空白。
- **排查：** 同时记录规范化版本、编码、算法名与摘要；必要时对输入字节输出长度和十六进制片段。

## 8. 关联知识点

- [状态模型、ORM、JSONB 与持久化边界](14_状态模型、ORM、JSONB_与持久化边界.md)
- [RAG 重复检测、语义缓存与 Best-of-n 采样](../02_Agent_RAG_Memory/09_重复检测、语义缓存与_Best-of-n_采样.md)
- [父子分块：层级切分、ID 映射与父块回取](../02_Agent_RAG_Memory/19_父子分块：层级切分、ID_映射与父块回取.md)

## 9. 参考资料与事实边界

- [RFC 1321：The MD5 Message-Digest Algorithm](https://www.rfc-editor.org/info/rfc1321)
- [RFC 6151：Updated Security Considerations for MD5](https://www.rfc-editor.org/info/rfc6151)
- [NIST FIPS 180-4：Secure Hash Standard](https://csrc.nist.gov/pubs/fips/180-4/final)
- [Python `hashlib` 文档](https://docs.python.org/3/library/hashlib.html)

本文示例中的文本规范化规则是工程示例，不是上述标准规定的唯一方案。

## 10. 复习检查问题

1. Hash 与加密的核心区别是什么？
2. 为什么 MD5 是 32 个十六进制字符，SHA-256 是 64 个？
3. 为什么输入空间无限意味着碰撞必然存在？
4. 文本内容 Hash 前为什么必须固定编码与规范化规则？
5. 为什么 SHA-256 不能直接替代密码哈希或 HMAC？
