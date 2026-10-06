import launch
import launch_ros

def generate_launch_description():
    
    # 地面分割节点
    terrain_analysis_node=launch_ros.actions.Node(
        package='terrain_analysis',
        executable='terrainAnalysis',
        name='terrain_analysis',
        output='screen',
        remappings=[
            ('/state_estimation', '/odin1/odometry'),  
            ('/registered_scan', '/odin1/cloud_slam')
        ],
        parameters=[
            {'scanVoxelSize': 0.05},      #预处理点云时的体素滤波大小（单位：米）
            {'decayTime': 1.5 }, #2.0     #点云衰减时间，超过此时间的旧点云会被清理 (单位：秒)
            {'noDecayDis': 0.5},          #在此距离内的点云不进行时间衰减处理（单位：米）
            {'clearingDis': 8.0},         #触发地图清理时的半径范围（单位：米）
            {'useSorting': True},         #是否使用排序法（分位数法）来估计地面高度
            {'quantileZ': 0.10}, #0.25    #地面高度分割时的Z值分位数）
            {'considerDrop': False},       #是否考虑地势下降（负高度差）的情况
            {'limitGroundLift': False},   #是否限制地面突然抬升的情况
            {'maxGroundLift': 0.15},      #限制地面突然抬升的最大高度（单位：米）
            {'clearDyObs': True},        #是否清理动态障碍物
            {'minDyObsDis': 0.5},         #动态障碍物的最小距离（单位：米），小于此距离的障碍物会被清理
            {'minDyObsAngle': 0.0},       #动态障碍物的最小角度（单位：度），小于此角度的障碍物会被清理
            {'minDyObsRelZ': -0.3},       #雷达距离地面的高度
            {'absDyObsRelZThre': 0.5},    #动态障碍物的绝对相对高度阈值（单位：米）
            {'minDyObsVFOV': -45.0},      #动态障碍物的最小垂直视场（单位：度）
            {'maxDyObsVFOV': 45.0},       #动态障碍物的最大垂直视场（单位：度）
            {'minDyObsHFOV': -60.0},      # 【新增】水平右侧边界
            {'maxDyObsHFOV': 60.0},       # 【新增】水平左侧边界
            {'minDyObsPointNum': 5},      #动态障碍物的最小点云数量
            {'noDataObstacle': False},    #是否允许无数据区域作为障碍物
            {'noDataBlockSkipNum': 0},    #无数据块的跳过数量
            {'minBlockPointNum': 10},     #最小块点云数量
            {'vehicleHeight': 0.5},       #车辆高度（单位：米）
            {'minObstacleHeight': 0.12},  #最小障碍物高度（单位：米）
            {'voxelPointUpdateThre': 100}, #体素点云更新阈值
            {'voxelTimeUpdateThre': 1.0}, #体素点云时间更新阈值
            {'minRelZ': -0.5},            #最小相对高度（单位：米）
            {'maxRelZ': 0.5},             #最大相对高度（单位：米）
            {'minScanDis': 0.5},         #最小扫描距离（单位：米）
            {'disRatioZ': 0.0}            #Z轴距离比例
        ]
    )

    return launch.LaunchDescription([
        terrain_analysis_node
    ])