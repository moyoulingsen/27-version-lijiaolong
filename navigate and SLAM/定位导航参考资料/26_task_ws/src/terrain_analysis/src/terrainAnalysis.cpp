#include <vector>
#include <cmath>
#include <algorithm>
#include <rclcpp/rclcpp.hpp>

#include <message_filters/subscriber.h>
#include <message_filters/sync_policies/approximate_time.h>
#include <message_filters/synchronizer.h>

#include <sensor_msgs/msg/point_cloud2.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <sensor_msgs/msg/joy.hpp>
#include <std_msgs/msg/float32.hpp>

#include <tf2/LinearMath/Quaternion.h>
#include <tf2/LinearMath/Matrix3x3.h>
#include <tf2_ros/transform_broadcaster.hpp>

#include <pcl/filters/voxel_grid.h>
#include <pcl/kdtree/kdtree_flann.h>
#include <pcl/point_cloud.h>
#include <pcl/point_types.h>
#include <pcl_conversions/pcl_conversions.h>

using namespace std;

class TerrainAnalysisNode : public rclcpp::Node
{
public:
    TerrainAnalysisNode() : Node("terrain_analysis")
    {
        // --- 在 ROS2 节点中声明并加载参数 --- //
        this->declare_parameters();
        this->get_parameters();

        // --- 设置订阅者和发布者 --- //
        subOdometry_ = this->create_subscription<nav_msgs::msg::Odometry>(
            "/state_estimation", 5, std::bind(&TerrainAnalysisNode::odometryHandler, this, std::placeholders::_1));
        subLaserCloud_ = this->create_subscription<sensor_msgs::msg::PointCloud2>(
            "/registered_scan", 5, std::bind(&TerrainAnalysisNode::laserCloudHandler, this, std::placeholders::_1));
        subJoystick_ = this->create_subscription<sensor_msgs::msg::Joy>(
            "/joy", 5, std::bind(&TerrainAnalysisNode::joystickHandler, this, std::placeholders::_1));
        subClearing_ = this->create_subscription<std_msgs::msg::Float32>(
            "/map_clearing", 5, std::bind(&TerrainAnalysisNode::clearingHandler, this, std::placeholders::_1));

        pubLaserCloud_ = this->create_publisher<sensor_msgs::msg::PointCloud2>("/terrain_map", 2);

        // --- 初始化数据结构 --- //
        for (int i = 0; i < terrainVoxelNum; i++) 
        {
            terrainVoxelCloud[i].reset(new pcl::PointCloud<pcl::PointXYZI>());
        }

        //设置下采样滤波器的体素大小
        downSizeFilter.setLeafSize(scanVoxelSize, scanVoxelSize, scanVoxelSize);
        
        // 定时器
        timer_ = this->create_wall_timer(
            10ms, std::bind(&TerrainAnalysisNode::timer_callback, this));
    }

private:

    const double PI = 3.1415926;
    // --- 算法参数 (会被ROS参数服务器的值覆盖) --- //
    double scanVoxelSize, decayTime, noDecayDis, clearingDis, quantileZ, maxGroundLift;
    double minDyObsDis, minDyObsAngle, minDyObsRelZ, absDyObsRelZThre;
    double minDyObsVFOV, maxDyObsVFOV, minDyObsHFOV, maxDyObsHFOV,vehicleHeight, voxelTimeUpdateThre,minObstacleHeight;
    double minRelZ, maxRelZ, disRatioZ, minScanDis;
    bool clearingCloud, useSorting, considerDrop, limitGroundLift, clearDyObs, noDataObstacle;
    int minDyObsPointNum, noDataBlockSkipNum, minBlockPointNum, voxelPointUpdateThre;

    // terrain voxel parameters
    // --- 地形体素栅格参数 (用于存储局部大地图) --- //
    float terrainVoxelSize = 1.0;
    int terrainVoxelShiftX = 0, terrainVoxelShiftY = 0;
    static const int terrainVoxelWidth = 21;
    int terrainVoxelHalfWidth = (terrainVoxelWidth - 1) / 2;
    static const int terrainVoxelNum = terrainVoxelWidth * terrainVoxelWidth;

    // planar voxel parameters
    // --- 平面体素栅格参数 (用于精细地面估计) --- //
    float planarVoxelSize = 0.2;
    static const int planarVoxelWidth = 51;
    int planarVoxelHalfWidth = (planarVoxelWidth - 1) / 2;
    static const int planarVoxelNum = planarVoxelWidth * planarVoxelWidth;

    // --- PCL点云对象指针 --- //
    pcl::PointCloud<pcl::PointXYZI>::Ptr laserCloud{new pcl::PointCloud<pcl::PointXYZI>()};
    pcl::PointCloud<pcl::PointXYZI>::Ptr laserCloudCrop{new pcl::PointCloud<pcl::PointXYZI>()};
    pcl::PointCloud<pcl::PointXYZI>::Ptr laserCloudDwz{new pcl::PointCloud<pcl::PointXYZI>()};
    pcl::PointCloud<pcl::PointXYZI>::Ptr terrainCloud{new pcl::PointCloud<pcl::PointXYZI>()};
    pcl::PointCloud<pcl::PointXYZI>::Ptr terrainCloudElev{new pcl::PointCloud<pcl::PointXYZI>()};
    pcl::PointCloud<pcl::PointXYZI>::Ptr terrainVoxelCloud[terrainVoxelNum];
    // --- PCL滤波器对象 --- //
    pcl::VoxelGrid<pcl::PointXYZI> downSizeFilter;

    // --- 状态与数据数组 --- //
    int terrainVoxelUpdateNum[terrainVoxelNum] = {0};
    float terrainVoxelUpdateTime[terrainVoxelNum] = {0};
    float planarVoxelElev[planarVoxelNum] = {0};
    int planarVoxelEdge[planarVoxelNum] = {0};
    int planarVoxelDyObs[planarVoxelNum] = {0};
    vector<float> planarPointElev[planarVoxelNum];

    // --- 系统状态变量 ---//
    double laserCloudTime = 0;
    bool newlaserCloud = false;
    double systemInitTime = 0;
    bool systemInited = false;
    int noDataInited = 0;
    rclcpp::Time savedTime;

    // --- 车辆位姿变量 --- //
    float vehicleRoll = 0, vehiclePitch = 0, vehicleYaw = 0;
    float vehicleX = 0, vehicleY = 0, vehicleZ = 0;
    float vehicleXRec = 0, vehicleYRec = 0;

    //车辆姿态角对应的正弦和余弦值
    float sinVehicleRoll = 0, cosVehicleRoll = 0;
    float sinVehiclePitch = 0, cosVehiclePitch = 0;
    float sinVehicleYaw = 0, cosVehicleYaw = 0;

    // --- 创建订阅者和发布者 --- //
    rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr subOdometry_;
    rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr subLaserCloud_;
    rclcpp::Subscription<sensor_msgs::msg::Joy>::SharedPtr subJoystick_;
    rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr subClearing_;
    rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr pubLaserCloud_;
    rclcpp::TimerBase::SharedPtr timer_;

    // 1. 声明所有参数并提供默认值
    void declare_parameters()
    {
        this->declare_parameter<double>("scanVoxelSize", 0.05);
        this->declare_parameter<double>("decayTime", 2.0);
        this->declare_parameter<double>("noDecayDis", 4.0);
        this->declare_parameter<double>("clearingDis", 8.0);
        this->declare_parameter<bool>("useSorting", true);
        this->declare_parameter<double>("quantileZ", 0.25);
        this->declare_parameter<bool>("considerDrop", false);
        this->declare_parameter<bool>("limitGroundLift", false);
        this->declare_parameter<double>("maxGroundLift", 0.15);
        this->declare_parameter<bool>("clearDyObs", false);
        this->declare_parameter<double>("minDyObsDis", 0.3);
        this->declare_parameter<double>("minDyObsAngle", 0.0);
        this->declare_parameter<double>("minDyObsRelZ", -0.5);
        this->declare_parameter<double>("absDyObsRelZThre", 0.2);
        this->declare_parameter<double>("minDyObsVFOV", -16.0);
        this->declare_parameter<double>("maxDyObsVFOV", 16.0);
        this->declare_parameter<double>("minDyObsHFOV", -60.0);
        this->declare_parameter<double>("maxDyObsHFOV", 60.0);
        this->declare_parameter<int>("minDyObsPointNum", 1);
        this->declare_parameter<bool>("noDataObstacle", false);
        this->declare_parameter<int>("noDataBlockSkipNum", 0);
        this->declare_parameter<int>("minBlockPointNum", 10);
        this->declare_parameter<double>("vehicleHeight", 1.5);
        this->declare_parameter<double>("minObstacleHeight", 0.1);
        this->declare_parameter<int>("voxelPointUpdateThre", 100);
        this->declare_parameter<double>("voxelTimeUpdateThre", 2.0);
        this->declare_parameter<double>("minRelZ", -1.5);
        this->declare_parameter<double>("maxRelZ", 0.5);
        this->declare_parameter<double>("minScanDis", 0.4);
        this->declare_parameter<double>("disRatioZ", 0.2);
    }
       
    // 2. 获取参数值并赋给成员变量
    void get_parameters()
    {
        this->get_parameter("scanVoxelSize", scanVoxelSize);
        this->get_parameter("decayTime", decayTime);
        this->get_parameter("noDecayDis", noDecayDis);
        this->get_parameter("clearingDis", clearingDis);
        this->get_parameter("useSorting", useSorting);
        this->get_parameter("quantileZ", quantileZ);
        this->get_parameter("considerDrop", considerDrop);
        this->get_parameter("limitGroundLift", limitGroundLift);
        this->get_parameter("maxGroundLift", maxGroundLift);
        this->get_parameter("clearDyObs", clearDyObs);
        this->get_parameter("minDyObsDis", minDyObsDis);
        this->get_parameter("minDyObsAngle", minDyObsAngle);
        this->get_parameter("minDyObsRelZ", minDyObsRelZ);
        this->get_parameter("absDyObsRelZThre", absDyObsRelZThre);
        this->get_parameter("minDyObsVFOV", minDyObsVFOV);
        this->get_parameter("maxDyObsVFOV", maxDyObsVFOV);
        this->get_parameter("minDyObsHFOV", minDyObsHFOV);
        this->get_parameter("maxDyObsHFOV", maxDyObsHFOV);
        this->get_parameter("minDyObsPointNum", minDyObsPointNum);
        this->get_parameter("noDataObstacle", noDataObstacle);
        this->get_parameter("noDataBlockSkipNum", noDataBlockSkipNum);
        this->get_parameter("minBlockPointNum", minBlockPointNum);
        this->get_parameter("vehicleHeight", vehicleHeight);
        this->get_parameter("minObstacleHeight", minObstacleHeight);
        this->get_parameter("voxelPointUpdateThre", voxelPointUpdateThre);
        this->get_parameter("voxelTimeUpdateThre", voxelTimeUpdateThre);
        this->get_parameter("minRelZ", minRelZ);
        this->get_parameter("maxRelZ", maxRelZ);
        this->get_parameter("minScanDis", minScanDis);
        this->get_parameter("disRatioZ", disRatioZ);
    }

    // 里程计回调函数
    void odometryHandler(const nav_msgs::msg::Odometry::SharedPtr odom)
    {
        double roll, pitch, yaw;
        tf2::Quaternion q(
            odom->pose.pose.orientation.x,
            odom->pose.pose.orientation.y,
            odom->pose.pose.orientation.z,
            odom->pose.pose.orientation.w);
        tf2::Matrix3x3(q).getRPY(roll, pitch, yaw);

        vehicleRoll = roll;
        vehiclePitch = pitch;
        vehicleYaw = yaw;
        vehicleX = odom->pose.pose.position.x;
        vehicleY = odom->pose.pose.position.y;
        vehicleZ = odom->pose.pose.position.z;
        // RCLCPP_INFO(this->get_logger(), "Odometry: [x: %f, y: %f, z: %f]", vehicleX, vehicleY, vehicleZ);

        sinVehicleRoll = sin(vehicleRoll);
        cosVehicleRoll = cos(vehicleRoll);
        sinVehiclePitch = sin(vehiclePitch);
        cosVehiclePitch = cos(vehiclePitch);
        sinVehicleYaw = sin(vehicleYaw);
        cosVehicleYaw = cos(vehicleYaw);

        if (noDataInited == 0) {
            vehicleXRec = vehicleX;
            vehicleYRec = vehicleY;
            noDataInited = 1;
        }
        if (noDataInited == 1) {
            float dis = sqrt(pow(vehicleX - vehicleXRec, 2) + pow(vehicleY - vehicleYRec, 2));
            if (dis >= noDecayDis)
                noDataInited = 2;
        }
    }

    // 激光点云回调函数
    void laserCloudHandler(const sensor_msgs::msg::PointCloud2::SharedPtr laserCloud2)
    {
        
        savedTime=laserCloud2->header.stamp;
        laserCloudTime = rclcpp::Time(savedTime).seconds();
        // RCLCPP_INFO(this->get_logger(), "Received laser cloud with timestamp: %f", laserCloudTime);

        if (!systemInited) {
            systemInitTime = laserCloudTime;
            systemInited = true;
        }

        laserCloud->clear();
        pcl::fromROSMsg(*laserCloud2, *laserCloud);

        pcl::PointXYZI point;
        laserCloudCrop->clear();
        int laserCloudSize = laserCloud->points.size();

        for (int i = 0; i < laserCloudSize; i++) {
          point = laserCloud->points[i];
          float dis = sqrt(pow(point.x - vehicleX, 2) + pow(point.y - vehicleY, 2));
          if (point.z - vehicleZ > minRelZ - disRatioZ * dis &&
              point.z - vehicleZ < maxRelZ + disRatioZ * dis &&
              dis >minScanDis &&
              dis < terrainVoxelSize * (terrainVoxelHalfWidth + 1)) {
              point.intensity = laserCloudTime - systemInitTime;
              laserCloudCrop->push_back(point);
          }
        }
        newlaserCloud = true;
    }

    void joystickHandler(const sensor_msgs::msg::Joy::SharedPtr joy) {
        if (joy->buttons[5] > 0.5) {
            noDataInited = 0;
            clearingCloud = true;
        }
    }

    void clearingHandler(const std_msgs::msg::Float32::SharedPtr dis) {
        noDataInited = 0;
        clearingDis = dis->data;
        clearingCloud = true;
    }

    void timer_callback()
    {
        if (!newlaserCloud) {
            return;
        }
        newlaserCloud = false;

        // ************************************ //
        // ********* 核心地形分析算法开始 ******** //
        // ************************************ //
        // terrain voxel roll over
        // --- 地形体素滚动 --- /
        float terrainVoxelCenX = terrainVoxelSize * terrainVoxelShiftX;
        float terrainVoxelCenY = terrainVoxelSize * terrainVoxelShiftY;

        while (vehicleX - terrainVoxelCenX < -terrainVoxelSize) {
          for (int indY = 0; indY < terrainVoxelWidth; indY++) {
            pcl::PointCloud<pcl::PointXYZI>::Ptr terrainVoxelCloudPtr =
                terrainVoxelCloud[terrainVoxelWidth * (terrainVoxelWidth - 1) +
                                  indY];
            for (int indX = terrainVoxelWidth - 1; indX >= 1; indX--) {
              terrainVoxelCloud[terrainVoxelWidth * indX + indY] =
                  terrainVoxelCloud[terrainVoxelWidth * (indX - 1) + indY];
            }
            terrainVoxelCloud[indY] = terrainVoxelCloudPtr;
            terrainVoxelCloud[indY]->clear();
          }
          terrainVoxelShiftX--;
          terrainVoxelCenX = terrainVoxelSize * terrainVoxelShiftX;
        }

        while (vehicleX - terrainVoxelCenX > terrainVoxelSize) {
          for (int indY = 0; indY < terrainVoxelWidth; indY++) {
            pcl::PointCloud<pcl::PointXYZI>::Ptr terrainVoxelCloudPtr =
                terrainVoxelCloud[indY];
            for (int indX = 0; indX < terrainVoxelWidth - 1; indX++) {
              terrainVoxelCloud[terrainVoxelWidth * indX + indY] =
                  terrainVoxelCloud[terrainVoxelWidth * (indX + 1) + indY];
            }
            terrainVoxelCloud[terrainVoxelWidth * (terrainVoxelWidth - 1) +
                              indY] = terrainVoxelCloudPtr;
            terrainVoxelCloud[terrainVoxelWidth * (terrainVoxelWidth - 1) + indY]
                ->clear();
          }
          terrainVoxelShiftX++;
          terrainVoxelCenX = terrainVoxelSize * terrainVoxelShiftX;
        }

        while (vehicleY - terrainVoxelCenY < -terrainVoxelSize) {
          for (int indX = 0; indX < terrainVoxelWidth; indX++) {
            pcl::PointCloud<pcl::PointXYZI>::Ptr terrainVoxelCloudPtr =
                terrainVoxelCloud[terrainVoxelWidth * indX +
                                  (terrainVoxelWidth - 1)];
            for (int indY = terrainVoxelWidth - 1; indY >= 1; indY--) {
              terrainVoxelCloud[terrainVoxelWidth * indX + indY] =
                  terrainVoxelCloud[terrainVoxelWidth * indX + (indY - 1)];
            }
            terrainVoxelCloud[terrainVoxelWidth * indX] = terrainVoxelCloudPtr;
            terrainVoxelCloud[terrainVoxelWidth * indX]->clear();
          }
          terrainVoxelShiftY--;
          terrainVoxelCenY = terrainVoxelSize * terrainVoxelShiftY;
        }

        while (vehicleY - terrainVoxelCenY > terrainVoxelSize) {
          for (int indX = 0; indX < terrainVoxelWidth; indX++) {
            pcl::PointCloud<pcl::PointXYZI>::Ptr terrainVoxelCloudPtr =
                terrainVoxelCloud[terrainVoxelWidth * indX];
            for (int indY = 0; indY < terrainVoxelWidth - 1; indY++) {
              terrainVoxelCloud[terrainVoxelWidth * indX + indY] =
                  terrainVoxelCloud[terrainVoxelWidth * indX + (indY + 1)];
            }
            terrainVoxelCloud[terrainVoxelWidth * indX +
                              (terrainVoxelWidth - 1)] = terrainVoxelCloudPtr;
            terrainVoxelCloud[terrainVoxelWidth * indX + (terrainVoxelWidth - 1)]
                ->clear();
          }
          terrainVoxelShiftY++;
          terrainVoxelCenY = terrainVoxelSize * terrainVoxelShiftY;
        }

        // stack registered laser scans
        // --- 将新点云堆叠到地形体素中 --- //
        pcl::PointXYZI point;
        int laserCloudCropSize = laserCloudCrop->points.size();
        for (int i = 0; i < laserCloudCropSize; i++) {
          point = laserCloudCrop->points[i];

          int indX = int((point.x - vehicleX + terrainVoxelSize / 2) /
                        terrainVoxelSize) +
                    terrainVoxelHalfWidth;
          int indY = int((point.y - vehicleY + terrainVoxelSize / 2) /
                        terrainVoxelSize) +
                    terrainVoxelHalfWidth;

          if (point.x - vehicleX + terrainVoxelSize / 2 < 0)
            indX--;
          if (point.y - vehicleY + terrainVoxelSize / 2 < 0)
            indY--;

          if (indX >= 0 && indX < terrainVoxelWidth && indY >= 0 &&
              indY < terrainVoxelWidth) {
            terrainVoxelCloud[terrainVoxelWidth * indX + indY]->push_back(point);
            terrainVoxelUpdateNum[terrainVoxelWidth * indX + indY]++;
          }
        }

        // --- 体素更新、降采样和衰减 ---//
        for (int ind = 0; ind < terrainVoxelNum; ind++) {
          if (terrainVoxelUpdateNum[ind] >= voxelPointUpdateThre ||
              laserCloudTime - systemInitTime - terrainVoxelUpdateTime[ind] >=
                  voxelTimeUpdateThre ||
              clearingCloud) {
            pcl::PointCloud<pcl::PointXYZI>::Ptr terrainVoxelCloudPtr =
                terrainVoxelCloud[ind];

            laserCloudDwz->clear();
            downSizeFilter.setInputCloud(terrainVoxelCloudPtr);
            downSizeFilter.filter(*laserCloudDwz);

            terrainVoxelCloudPtr->clear();
            int laserCloudDwzSize = laserCloudDwz->points.size();
            for (int i = 0; i < laserCloudDwzSize; i++) {
              point = laserCloudDwz->points[i];
              float dis = sqrt((point.x - vehicleX) * (point.x - vehicleX) +
                              (point.y - vehicleY) * (point.y - vehicleY));
              if (point.z - vehicleZ > minRelZ - disRatioZ * dis &&
                  point.z - vehicleZ < maxRelZ + disRatioZ * dis &&
                  (laserCloudTime - systemInitTime - point.intensity <
                      decayTime ||
                  dis < noDecayDis) &&
                  !(dis < clearingDis && clearingCloud)) {
                terrainVoxelCloudPtr->push_back(point);
              }
            }

            terrainVoxelUpdateNum[ind] = 0;
            terrainVoxelUpdateTime[ind] = laserCloudTime - systemInitTime;
          }
        }

        // --- 提取车辆周围的点云用于地面估计 --- //
        terrainCloud->clear();
        // 从地形体素栅格的中心区域(11x11)提取点云
        for (int indX = terrainVoxelHalfWidth - 5;
            indX <= terrainVoxelHalfWidth + 5; indX++) {
          for (int indY = terrainVoxelHalfWidth - 5;
              indY <= terrainVoxelHalfWidth + 5; indY++) {
            *terrainCloud += *terrainVoxelCloud[terrainVoxelWidth * indX + indY];
          }
        }

        // estimate ground and compute elevation for each point
        // --- 提取车辆周围的点云用于地面估计 --- //
        for (int i = 0; i < planarVoxelNum; i++) {
          planarVoxelElev[i] = 0;
          planarVoxelEdge[i] = 0;
          planarVoxelDyObs[i] = 0;
          planarPointElev[i].clear();
        }

        // 遍历车辆周围的点云，将其投影到更精细的平面体素栅格中
        int terrainCloudSize = terrainCloud->points.size();
        for (int i = 0; i < terrainCloudSize; i++) {
          point = terrainCloud->points[i];

          int indX =
              int((point.x - vehicleX + planarVoxelSize / 2) / planarVoxelSize) +
              planarVoxelHalfWidth;
          int indY =
              int((point.y - vehicleY + planarVoxelSize / 2) / planarVoxelSize) +
              planarVoxelHalfWidth;

          if (point.x - vehicleX + planarVoxelSize / 2 < 0)
            indX--;
          if (point.y - vehicleY + planarVoxelSize / 2 < 0)
            indY--;

          if (point.z - vehicleZ > minRelZ && point.z - vehicleZ < maxRelZ) {
            for (int dX = -1; dX <= 1; dX++) {
              for (int dY = -1; dY <= 1; dY++) {
                if (indX + dX >= 0 && indX + dX < planarVoxelWidth &&
                    indY + dY >= 0 && indY + dY < planarVoxelWidth) {
                  planarPointElev[planarVoxelWidth * (indX + dX) + indY + dY]
                      .push_back(point.z);
                }
              }
            }
          }

          // 动态障碍物检测与标记
          if (clearDyObs) {
            if (indX >= 0 && indX < planarVoxelWidth && indY >= 0 &&
                indY < planarVoxelWidth) {
              float pointX1 = point.x - vehicleX;
              float pointY1 = point.y - vehicleY;
              float pointZ1 = point.z - vehicleZ;

              float dis1 = sqrt(pointX1 * pointX1 + pointY1 * pointY1);
              if (dis1 > minDyObsDis) {
                float angle1 = atan2(pointZ1 - minDyObsRelZ, dis1) * 180.0 / PI;
                if (angle1 > minDyObsAngle) {
                  float pointX2 =
                      pointX1 * cosVehicleYaw + pointY1 * sinVehicleYaw;
                  float pointY2 =
                      -pointX1 * sinVehicleYaw + pointY1 * cosVehicleYaw;
                  float pointZ2 = pointZ1;

                  float pointX3 =
                      pointX2 * cosVehiclePitch - pointZ2 * sinVehiclePitch;
                  float pointY3 = pointY2;
                  float pointZ3 =
                      pointX2 * sinVehiclePitch + pointZ2 * cosVehiclePitch;

                  float pointX4 = pointX3;
                  float pointY4 =
                      pointY3 * cosVehicleRoll + pointZ3 * sinVehicleRoll;
                  float pointZ4 =
                      -pointY3 * sinVehicleRoll + pointZ3 * cosVehicleRoll;

                  float dis4 = sqrt(pointX4 * pointX4 + pointY4 * pointY4);
                  float angle4 = atan2(pointZ4, dis4) * 180.0 / PI;
                  float hAngle = atan2(pointY4, pointX4) * 180.0 / PI;
                  if (hAngle > minDyObsHFOV && hAngle < maxDyObsHFOV) {
                    if ((angle4 > minDyObsVFOV && angle4 < maxDyObsVFOV) || (fabs(pointZ4) < absDyObsRelZThre)) {
                      planarVoxelDyObs[planarVoxelWidth * indX + indY]++;
                    }
                  }
                }
              } else {
                planarVoxelDyObs[planarVoxelWidth * indX + indY] +=
                    minDyObsPointNum;
              }
            }
          }
        }

        if (clearDyObs) {
          for (int i = 0; i < laserCloudCropSize; i++) {
            point = laserCloudCrop->points[i];

            int indX = int((point.x - vehicleX + planarVoxelSize / 2) /
                          planarVoxelSize) +
                      planarVoxelHalfWidth;
            int indY = int((point.y - vehicleY + planarVoxelSize / 2) /
                          planarVoxelSize) +
                      planarVoxelHalfWidth;

            if (point.x - vehicleX + planarVoxelSize / 2 < 0)
              indX--;
            if (point.y - vehicleY + planarVoxelSize / 2 < 0)
              indY--;

            if (indX >= 0 && indX < planarVoxelWidth && indY >= 0 &&
                indY < planarVoxelWidth) {
              float pointX1 = point.x - vehicleX;
              float pointY1 = point.y - vehicleY;
              float pointZ1 = point.z - vehicleZ;

              float dis1 = sqrt(pointX1 * pointX1 + pointY1 * pointY1);
              float angle1 = atan2(pointZ1 - minDyObsRelZ, dis1) * 180.0 / PI;
              if (angle1 > minDyObsAngle) {
                planarVoxelDyObs[planarVoxelWidth * indX + indY] = 0;
              }
            }
          }
        }

        // --- 确定每个平面体素的地面高度 --- //
        if (useSorting) {
          // 排序法：对每个平面体素内的高度值排序，取分位数作为地面高度
          for (int i = 0; i < planarVoxelNum; i++) {
            int planarPointElevSize = planarPointElev[i].size();
            if (planarPointElevSize > 0) {
              sort(planarPointElev[i].begin(), planarPointElev[i].end());

              int quantileID = int(quantileZ * planarPointElevSize);
              if (quantileID < 0)
                quantileID = 0;
              else if (quantileID >= planarPointElevSize)
                quantileID = planarPointElevSize - 1;

              if (planarPointElev[i][quantileID] >
                      planarPointElev[i][0] + maxGroundLift &&
                  limitGroundLift) {
                planarVoxelElev[i] = planarPointElev[i][0] + maxGroundLift;
              } else {
                planarVoxelElev[i] = planarPointElev[i][quantileID];
              }
            }
          }
        } else {
          // 最低点法：取最低点的高度作为地面高度
          for (int i = 0; i < planarVoxelNum; i++) {
            int planarPointElevSize = planarPointElev[i].size();
            if (planarPointElevSize > 0) {
              float minZ = 1000.0;
              int minID = -1;
              for (int j = 0; j < planarPointElevSize; j++) {
                if (planarPointElev[i][j] < minZ) {
                  minZ = planarPointElev[i][j];
                  minID = j;
                }
              }

              if (minID != -1) {
                planarVoxelElev[i] = planarPointElev[i][minID];
              }
            }
          }
        }

        // --- 生成最终的带离地高度的点云 --- //
        terrainCloudElev->clear();
        int terrainCloudElevSize = 0;
        for (int i = 0; i < terrainCloudSize; i++) {
          point = terrainCloud->points[i];
          if (point.z - vehicleZ > minRelZ && point.z - vehicleZ < maxRelZ) {
            int indX = int((point.x - vehicleX + planarVoxelSize / 2) /
                          planarVoxelSize) +
                      planarVoxelHalfWidth;
            int indY = int((point.y - vehicleY + planarVoxelSize / 2) /
                          planarVoxelSize) +
                      planarVoxelHalfWidth;

            if (point.x - vehicleX + planarVoxelSize / 2 < 0)
              indX--;
            if (point.y - vehicleY + planarVoxelSize / 2 < 0)
              indY--;

            if (indX >= 0 && indX < planarVoxelWidth && indY >= 0 &&
                indY < planarVoxelWidth) {
              if (planarVoxelDyObs[planarVoxelWidth * indX + indY] <
                      minDyObsPointNum ||
                  !clearDyObs) {
                // 计算点的高度与所在平面体素地面高度的差值
                float disZ =
                    point.z - planarVoxelElev[planarVoxelWidth * indX + indY];
                if (considerDrop)
                  disZ = fabs(disZ);
                int planarPointElevSize =
                    planarPointElev[planarVoxelWidth * indX + indY].size();
                // 如果差值在合理范围内，则认为是有效障碍物点
                if (disZ >= minObstacleHeight && disZ < vehicleHeight &&
                    planarPointElevSize >= minBlockPointNum) {
                  terrainCloudElev->push_back(point);
                  terrainCloudElev->points[terrainCloudElevSize].intensity = disZ;

                  terrainCloudElevSize++;
                }
              }
            }
          }
        }

        // 为无数据区域添加虚拟障碍物
        if (noDataObstacle && noDataInited == 2) {
          for (int i = 0; i < planarVoxelNum; i++) {
            int planarPointElevSize = planarPointElev[i].size();
            if (planarPointElevSize < minBlockPointNum) {
              planarVoxelEdge[i] = 1;
            }
          }

          for (int noDataBlockSkipCount = 0;
              noDataBlockSkipCount < noDataBlockSkipNum;
              noDataBlockSkipCount++) {
            for (int i = 0; i < planarVoxelNum; i++) {
              if (planarVoxelEdge[i] >= 1) {
                int indX = int(i / planarVoxelWidth);
                int indY = i % planarVoxelWidth;
                bool edgeVoxel = false;
                for (int dX = -1; dX <= 1; dX++) {
                  for (int dY = -1; dY <= 1; dY++) {
                    if (indX + dX >= 0 && indX + dX < planarVoxelWidth &&
                        indY + dY >= 0 && indY + dY < planarVoxelWidth) {
                      if (planarVoxelEdge[planarVoxelWidth * (indX + dX) + indY +
                                          dY] < planarVoxelEdge[i]) {
                        edgeVoxel = true;
                      }
                    }
                  }
                }

                if (!edgeVoxel)
                  planarVoxelEdge[i]++;
              }
            }
          }

          for (int i = 0; i < planarVoxelNum; i++) {
            if (planarVoxelEdge[i] > noDataBlockSkipNum) {
              int indX = int(i / planarVoxelWidth);
              int indY = i % planarVoxelWidth;

              point.x =
                  planarVoxelSize * (indX - planarVoxelHalfWidth) + vehicleX;
              point.y =
                  planarVoxelSize * (indY - planarVoxelHalfWidth) + vehicleY;
              point.z = vehicleZ;
              point.intensity = vehicleHeight;

              point.x -= planarVoxelSize / 4.0;
              point.y -= planarVoxelSize / 4.0;
              terrainCloudElev->push_back(point);

              point.x += planarVoxelSize / 2.0;
              terrainCloudElev->push_back(point);

              point.y += planarVoxelSize / 2.0;
              terrainCloudElev->push_back(point);

              point.x -= planarVoxelSize / 2.0;
              terrainCloudElev->push_back(point);
            }
          }
        }

        clearingCloud = false;

        // publish points with elevation
        // --- 发布地形图 --- //
        sensor_msgs::msg::PointCloud2 terrainCloud2;
        pcl::toROSMsg(*terrainCloudElev, terrainCloud2);
        terrainCloud2.header.stamp = savedTime;
        // RCLCPP_INFO(this->get_logger(), "Publishing terrain cloud with timestamp: %f", laserCloudTime);
        terrainCloud2.header.frame_id = "odom";
        pubLaserCloud_->publish(terrainCloud2);
    }
};

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<TerrainAnalysisNode>());
    rclcpp::shutdown();
    return 0;
}