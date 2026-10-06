# 📝 项目介绍

此项目是对定位导航参考资料作出的一些小的修改及由ROS1对ROS2的适配

## 一、basic_task：运动插件相关修改

在运动插件实现示例文件`car_drive.gazebo`的处理上，主要进行了一些未用到部分的删减，具体如下：



1.  **删除未用部分**

    移除了`ros2_control`和轮子相关的代码片段。原因是所使用的插件`libgazebo_ros_planar_move.so`是通用的平面运动控制器，不依赖具体轮子结构,其具体功能可参考文件夹中提供的源码`gazebo_ros_planar_move.cpp`。

2.  **代码优化建议**

    以下与轮子相关的参数配置（涉及摩擦系数、刚度系数、阻尼系数等），建议放入轮子的 xacro 文件中，可使代码结构更简洁：



```
<!-- mu1：静摩擦系数；mu2：动摩擦系数；kp：刚度系数；kd：阻尼系数 -->
<gazebo reference="${wheel_name}_link">
    <mu1>0.0</mu1>
    <mu2>0.0</mu2>
    <kp>20000.0</kp>
    <kd>10.0</kd>
    <minDepth>0.001</minDepth>
    <maxVel>100.0</maxVel>
</gazebo>
```

## 二、velodyne_simulator：雷达仿真包的 ROS2 适配及问题修正

该部分针对雷达仿真包进行处理。原仿真包基于 ROS1 开发，因此在 GitHub 上选用了 ROS2 版本（[仓库地址](https://github.com/ToyotaResearchInstitute/velodyne_simulator)），但该版本存在部分问题，需手动修正后才能正常使用（文档未同步更新，需自行操作）。

### （1）修正日志输出参数缺失问题

文件路径：`velodyne_simulator/velodyne_gazebo_plugins/src/GazeboRosVelodyneLaser.cpp`

**问题描述**：第 295 行的日志输出代码`RCLCPP_INFO(ros_node_->get_logger(), "Velodyne %slaser plugin ready");`中，`%s`格式占位符缺少对应的字符串参数。

**解决方法**：补充缺失的参数，或直接删除`%s`。

### （2）修正 xacro 标签格式错误

文件路径：`velodyne_simulator/velodyne_description/urdf/example.urdf.xacro`

**问题描述**：文件中`<VLP-16 />`标签格式不符合 xacro 语法要求。

**解决方法**：将其修改为`<xacro:VLP-16 />`格式，修改后代码如下：



```
<xacro:include filename="$(find velodyne_description)/urdf/VLP-16.urdf.xacro"/>
<xacro:VLP-16 parent="base_link" name="velodyne" topic="/velodyne_points" hz="10" samples="440" gpu="${gpu}">
    <origin xyz="0 0 0.4" rpy="0 0 0" />
</xacro:VLP-16>
```

### （3）修正模型文件路径错误

文件路径：`velodyne_simulator/velodyne_description/urdf/VLP-16.urdf.xacro`

**问题描述**：模型文件路径使用`package://`格式，可能导致 Gazebo 无法加载资源

**解决方法**：将路径格式修改为`file://$(find package_name)`，具体如下：

原代码：



```
<geometry>
    <mesh filename="package://velodyne_description/meshes/VLP16_base_1.dae"/>
</geometry>
```

修改后：


```
<geometry>
    <mesh filename="file://$(find velodyne_description)/meshes/VLP16_base_1.dae"/>
</geometry>
```
具体原因自行查阅

**参考资料**：[如何解决 RViz2 无法加载资源的错误](https://techoverflow.net/2025/01/08/how-to-fix-rviz2-error-could-not-load-resource-unable-to-open-file/)
