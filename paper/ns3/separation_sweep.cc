/*
 * ns-3 Experiment 2: Two-Link Separation Sweep (Hidden Terminal Transition)
 *
 * Two parallel 30m links at varying separation s.
 * Tests transition from contention regime to hidden terminal regime
 * at the CS boundary (~71.2m).
 *
 * Usage: ./ns3 run scratch/separation_sweep -- --separation=75 --seed=1
 *        ./ns3 run scratch/separation_sweep -- --separation=75 --seed=1 --idealMcs=true
 */

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/wifi-module.h"
#include "ns3/mobility-module.h"
#include "ns3/applications-module.h"

#include <fstream>
#include <iomanip>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("SeparationSweep");

int
main(int argc, char* argv[])
{
    double separation = 50.0;  // meters between link pairs
    uint32_t seed = 1;
    double simTime = 30.0;
    double warmup = 2.0;
    bool idealMcs = false;     // false=fixed HeMcs5, true=IdealWifiManager
    std::string outDir = "/results";

    CommandLine cmd(__FILE__);
    cmd.AddValue("separation", "Vertical separation between link pairs (m)", separation);
    cmd.AddValue("seed", "RNG seed", seed);
    cmd.AddValue("simTime", "Simulation time in seconds", simTime);
    cmd.AddValue("idealMcs", "Use IdealWifiManager for adaptive MCS", idealMcs);
    cmd.AddValue("outDir", "Output directory for CSV", outDir);
    cmd.Parse(argc, argv);

    RngSeedManager::SetSeed(seed);
    RngSeedManager::SetRun(seed);

    uint32_t nLinks = 2;

    // --- Create nodes ---
    NodeContainer staNodes;
    staNodes.Create(nLinks);
    NodeContainer apNodes;
    apNodes.Create(nLinks);

    // --- WiFi PHY + Channel ---
    YansWifiChannelHelper channel;
    channel.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel");
    channel.AddPropagationLoss("ns3::LogDistancePropagationLossModel",
                               "Exponent", DoubleValue(3.0),
                               "ReferenceLoss", DoubleValue(46.4));

    YansWifiPhyHelper phy;
    phy.SetChannel(channel.Create());
    phy.Set("TxPowerStart", DoubleValue(20.0));
    phy.Set("TxPowerEnd", DoubleValue(20.0));
    phy.Set("CcaEdThreshold", DoubleValue(-82.0));
    phy.Set("RxNoiseFigure", DoubleValue(6.0));
    // Force 20 MHz channel to match ncsim's MCS table (HeMcs5 @ 20 MHz = 68.8 Mbps)
    phy.Set("ChannelSettings", StringValue("{0, 20, BAND_5GHZ, 0}"));

    // --- WiFi MAC ---
    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211ax);

    if (idealMcs)
    {
        wifi.SetRemoteStationManager("ns3::IdealWifiManager");
    }
    else
    {
        wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                      "DataMode", StringValue("HeMcs5"),
                                      "ControlMode", StringValue("HeMcs0"));
    }

    WifiMacHelper mac;
    Ssid ssid = Ssid("ns3-separation");

    mac.SetType("ns3::StaWifiMac",
                "Ssid", SsidValue(ssid),
                "ActiveProbing", BooleanValue(false));
    NetDeviceContainer staDevices = wifi.Install(phy, mac, staNodes);

    mac.SetType("ns3::ApWifiMac",
                "Ssid", SsidValue(ssid));
    NetDeviceContainer apDevices = wifi.Install(phy, mac, apNodes);

    // --- Disable A-MPDU and A-MSDU, set guard interval to 800ns (match ncsim MCS table) ---
    for (uint32_t i = 0; i < nLinks; ++i)
    {
        Ptr<WifiNetDevice> staDev = DynamicCast<WifiNetDevice>(staDevices.Get(i));
        staDev->GetMac()->SetAttribute("BE_MaxAmpduSize", UintegerValue(0));
        staDev->GetMac()->SetAttribute("BK_MaxAmpduSize", UintegerValue(0));
        staDev->GetMac()->SetAttribute("VI_MaxAmpduSize", UintegerValue(0));
        staDev->GetMac()->SetAttribute("VO_MaxAmpduSize", UintegerValue(0));
        staDev->GetMac()->SetAttribute("BE_MaxAmsduSize", UintegerValue(0));
        staDev->GetMac()->SetAttribute("BK_MaxAmsduSize", UintegerValue(0));
        staDev->GetMac()->SetAttribute("VI_MaxAmsduSize", UintegerValue(0));
        staDev->GetMac()->SetAttribute("VO_MaxAmsduSize", UintegerValue(0));
        staDev->GetHeConfiguration()->SetAttribute("GuardInterval",
                                                     TimeValue(NanoSeconds(800)));

        Ptr<WifiNetDevice> apDev = DynamicCast<WifiNetDevice>(apDevices.Get(i));
        apDev->GetMac()->SetAttribute("BE_MaxAmpduSize", UintegerValue(0));
        apDev->GetMac()->SetAttribute("BK_MaxAmpduSize", UintegerValue(0));
        apDev->GetMac()->SetAttribute("VI_MaxAmpduSize", UintegerValue(0));
        apDev->GetMac()->SetAttribute("VO_MaxAmpduSize", UintegerValue(0));
        apDev->GetMac()->SetAttribute("BE_MaxAmsduSize", UintegerValue(0));
        apDev->GetMac()->SetAttribute("BK_MaxAmsduSize", UintegerValue(0));
        apDev->GetMac()->SetAttribute("VI_MaxAmsduSize", UintegerValue(0));
        apDev->GetMac()->SetAttribute("VO_MaxAmsduSize", UintegerValue(0));
        apDev->GetHeConfiguration()->SetAttribute("GuardInterval",
                                                    TimeValue(NanoSeconds(800)));
    }

    // --- Disable RTS/CTS ---
    Config::SetDefault("ns3::WifiRemoteStationManager::RtsCtsThreshold",
                       StringValue("999999"));

    // --- Mobility ---
    // Link A: STA at (0,0), AP at (30,0)
    // Link B: STA at (0,separation), AP at (30,separation)
    MobilityHelper mobility;
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");

    Ptr<ListPositionAllocator> staPos = CreateObject<ListPositionAllocator>();
    staPos->Add(Vector(0.0, 0.0, 0.0));
    staPos->Add(Vector(0.0, separation, 0.0));
    mobility.SetPositionAllocator(staPos);
    mobility.Install(staNodes);

    Ptr<ListPositionAllocator> apPos = CreateObject<ListPositionAllocator>();
    apPos->Add(Vector(30.0, 0.0, 0.0));
    apPos->Add(Vector(30.0, separation, 0.0));
    mobility.SetPositionAllocator(apPos);
    mobility.Install(apNodes);

    // --- Internet stack ---
    InternetStackHelper internet;
    internet.Install(staNodes);
    internet.Install(apNodes);

    Ipv4AddressHelper ipv4;
    ipv4.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer staInterfaces = ipv4.Assign(staDevices);
    Ipv4InterfaceContainer apInterfaces = ipv4.Assign(apDevices);

    // --- Saturated UDP traffic ---
    uint16_t port = 9;
    uint32_t packetSize = 1472;
    std::string dataRate = "200Mbps";

    for (uint32_t i = 0; i < nLinks; ++i)
    {
        PacketSinkHelper sinkHelper("ns3::UdpSocketFactory",
                                     InetSocketAddress(Ipv4Address::GetAny(), port + i));
        ApplicationContainer sinkApp = sinkHelper.Install(apNodes.Get(i));
        sinkApp.Start(Seconds(0.0));
        sinkApp.Stop(Seconds(simTime));

        OnOffHelper onoff("ns3::UdpSocketFactory",
                           InetSocketAddress(apInterfaces.GetAddress(i), port + i));
        onoff.SetAttribute("DataRate", DataRateValue(DataRate(dataRate)));
        onoff.SetAttribute("PacketSize", UintegerValue(packetSize));
        onoff.SetAttribute("OnTime", StringValue("ns3::ConstantRandomVariable[Constant=1]"));
        onoff.SetAttribute("OffTime", StringValue("ns3::ConstantRandomVariable[Constant=0]"));

        ApplicationContainer onoffApp = onoff.Install(staNodes.Get(i));
        onoffApp.Start(Seconds(0.5));
        onoffApp.Stop(Seconds(simTime));
    }

    Simulator::Stop(Seconds(simTime));
    Simulator::Run();

    // --- Collect results ---
    double measureTime = simTime - 0.5;  // GetTotalRx counts from t=0; subtract app start offset

    std::string mcsTag = idealMcs ? "ideal" : "fixed";
    std::string fname = outDir + "/separation_s" + std::to_string((int)separation)
                        + "_" + mcsTag + "_seed" + std::to_string(seed) + ".csv";
    std::ofstream ofs(fname);
    ofs << "separation,mcs_mode,seed,link_index,goodput_Mbps,goodput_MBps" << std::endl;

    for (uint32_t i = 0; i < nLinks; ++i)
    {
        Ptr<PacketSink> sink = DynamicCast<PacketSink>(
            apNodes.Get(i)->GetApplication(0));
        uint64_t totalRx = sink->GetTotalRx();

        double goodputMbps = (totalRx * 8.0) / (measureTime * 1e6);
        double goodputMBps = totalRx / (measureTime * 1e6);

        ofs << separation << "," << mcsTag << "," << seed << "," << i << ","
            << std::fixed << std::setprecision(4)
            << goodputMbps << "," << goodputMBps << std::endl;
    }
    ofs.close();

    Simulator::Destroy();

    std::cout << "sep=" << separation << " mcs=" << mcsTag
              << " seed=" << seed << " -> " << fname << std::endl;

    return 0;
}
