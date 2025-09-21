# 深度学习
![alt text](images\image.png)
![al t text](images\image-1.png)
过拟合（offerfitting）：机器学习模型在训练数据上表现很好(比如准确率极高)但在新数据(测试集或实际应用场景)上表现明显下降的现象

### 深度学习框架：Keras+TensorFlow

## 一.线性回归模型&梯度下降法
### 1.线性回归模型定义
![alt text](images\image-3.png)
> w~i~为权重参数；b为偏置值
> y~i~为已提供的目标属性样本值
> 实际可能会得到不止一组（**w**,b），那么需要计算和样本间的平均距离，选取损失最小的
### 2.误差函数
![alt text](images\image-4.png)
> 用于评判所得到的参数（**w**,b）
### 3.参数求解
#### 1).穷举
#### 2).最小二乘法
##### 非向量形式
二次函数求最小值
![alt text](images\image-5.png)
![alt text](images\image-6.png)
##### 向量形式
![alt text](images\image-7.png)
![alt text](images\image-8.png)
**----矩阵求导----**
![alt text](images\image-9.png) 
> 但(X^T^X)^-1^可能无解，所以最小二乘法不一定可以求解
### 4，梯度下降法
![alt text](images\image-10.png)
> 求导求出梯度（上升变化最快）取负，也就是确定了下降最快的方向；
> a为参数，控制在上一步确定的方向上移动的距离；
#### 案例
![alt text](images\image-11.png)
#### 多参数求解
求偏导

---
## 二.逻辑回归
### 1.回归vs分类
1. 有监督学习：数据带标签
   - 回归任务
   - 分类任务
   - ![alt text](images\image12.png)
2. 无监督学习：数据不带标签 -> 如 聚类

### 2.算法原理
![alt text](images/image13.png)
