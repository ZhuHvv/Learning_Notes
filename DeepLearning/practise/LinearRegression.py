# 定义数据集

#定义数据特征
x_data = [1,2,3]

#定义数据标签
y_data = [2,4,6]

# 初始化参数
w=4

#定义线性回归模型
def forward(x):
    return x*w

# 定义损失函数
def loss(xs,ys):
    costValue=0
    for x,y in zip(xs,ys):
        y_pred=forward(x)
        costValue+=(y_pred-y)**2
    return costValue/len(xs)/2

# 定义梯度计算函数
def gradient(xs,ys):
    grad=0
    for x,y in zip(xs,ys):
        grad+=x*(forward(x)-y)
    return grad/len(xs)

for epoch in range(200):
    #计算误差损失
    costValue=loss(x_data,y_data)
    
    grad=gradient(x_data,y_data)
    
    w=w-0.01*grad
    
    print("epoch:",epoch,"w=",w,"loss=",costValue)
    
print("Predict (after training)",4,forward(4))