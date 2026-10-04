``` xml
<root BTCPP_format="4">\
<!--1.第一个标签是 <root>不能改。
否则 BehaviorTree.CPP 解析时会找不到根元素而报错。
2.BTCPP_format="4"：表示 BehaviorTree.CPP 的 XML 格式版本-->
     <BehaviorTree ID="MainTree"><!-- 行为树id不能省略-->
        <Sequence name="root_sequence"><!--name可以，但建议写-->
            <SaySomething   name="action_hello" message="Hello"/>
<!--factory.registerNodeType<SaySomething>("SaySomething");
<SaySomething>：尖括号里是 C++ 类名。
"SaySomething"：括号里是 XML 中使用的标签名字符串。

把 C++ 类 SaySomething 注册到工厂里，注册名是 "SaySomething"。
-->
            <OpenGripper    name="open_gripper"/>
            <ApproachObject name="approach_object"/>
            <CloseGripper   name="close_gripper"/>
        </Sequence>
     </BehaviorTree>
 </root>

```

In terms of number of children:
在子女数量方面：
+ ControlNodes contain 1 to N children.
ControlNodes 包含 1 到 N 个子节点。
+ DecoratorNodes and Subtrees contain only 1 child.
DecoratorNodes 及其子树都只包含 1 个子节点。
+ ActionNodes and ConditionNodes have no child.
ActionNodes 和 ConditionNodes 没有孩子。

节点类别、能不能有子节点、有几个子节点、执行时干什么”都是在 C++ 里定义的，不是在 XML 里定义的。