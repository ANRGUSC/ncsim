/*
 * ns-3 single-link rate and RTS/CTS overhead validation (1 m high-SNR link)
 *
 * n = 1..8 co-located 802.11ax link pairs, all within carrier sensing range.
 * Measures per-station saturated UDP goodput.
 *
 * Validates ncsim's Bianchi eta(n)/n efficiency curve.
 *
 * Usage: ./ns3 run scratch/contention_scaling -- --nLinks=4 --seed=1
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

NS_LOG_COMPONENT_DEFINE("ContentionScaling");

// Global counters for received bytes per STA
std::vector<uint64_t> g_rxBytes;

void
RxCallback(uint32_t index, Ptr<const Packet> packet, const Address& address)
{
    g_rxBytes[index] += packet->GetSize();
}

int
main(int argc, char* argv[])
{
    uint32_t nLinks = 1;
    uint32_t mcs = 0;
    bool rts = false;
    uint32_t seed = 1;
    double simTime = 30.0;     // seconds
    // Measurement includes traffic from application start at 0.5 s.
    std::string outDir = "/results";

    CommandLine cmd(__FILE__);
    cmd.AddValue("nLinks", "Number of STA-AP link pairs", nLinks);
    cmd.AddValue("seed", "RNG seed", seed);
    cmd.AddValue("simTime", "Simulation time in seconds", simTime);
    cmd.AddValue("outDir", "Output directory for CSV", outDir);
    cmd.AddValue("mcs", "HE MCS index (0 or 11 for bounded validation)", mcs);
    cmd.AddValue("rts", "Enable RTS/CTS", rts);
    cmd.Parse(argc, argv);
    Config::SetDefault("ns3::WifiRemoteStationManager::RtsCtsThreshold",
                       UintegerValue(rts ? 0 : 999999));

    RngSeedManager::SetSeed(seed);
    RngSeedManager::SetRun(seed);

    g_rxBytes.resize(nLinks, 0);

    // --- Create nodes: n STAs + n APs ---
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
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                  "DataMode", StringValue("HeMcs" + std::to_string(mcs)),
                                  "ControlMode", StringValue("OfdmRate24Mbps"));

    WifiMacHelper mac;

    // Install on each STA-AP pair using same SSID
    // All on same channel so they contend
    NetDeviceContainer staDevices;
    NetDeviceContainer apDevices;

    Ssid ssid = Ssid("ns3-contention");

    mac.SetType("ns3::StaWifiMac",
                "Ssid", SsidValue(ssid),
                "ActiveProbing", BooleanValue(false));
    staDevices = wifi.Install(phy, mac, staNodes);

    mac.SetType("ns3::ApWifiMac",
                "Ssid", SsidValue(ssid));
    apDevices = wifi.Install(phy, mac, apNodes);

    // --- Disable A-MPDU and A-MSDU (critical for Bianchi single-frame match) ---
    // Set guard interval to 800ns to match ncsim's MCS table (0.8us GI)
    for (uint32_t i = 0; i < nLinks; ++i)
    {
        // STA devices
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

        // AP devices
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

    // RTS/CTS threshold was set before constructing the managers.

    // --- Mobility: STAs at (0, i*5), APs at (1, i*5) ---
    MobilityHelper mobility;
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");

    Ptr<ListPositionAllocator> staPos = CreateObject<ListPositionAllocator>();
    Ptr<ListPositionAllocator> apPos = CreateObject<ListPositionAllocator>();
    for (uint32_t i = 0; i < nLinks; ++i)
    {
        staPos->Add(Vector(0.0, i * 5.0, 0.0));
        apPos->Add(Vector(1.0, i * 5.0, 0.0));
    }

    mobility.SetPositionAllocator(staPos);
    mobility.Install(staNodes);
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

    // --- Saturated UDP traffic: STA -> AP ---
    uint16_t port = 9;
    uint32_t packetSize = 1472;  // bytes (standard UDP payload)
    // High enough rate to saturate: 200 Mbps per STA
    std::string dataRate = "200Mbps";

    for (uint32_t i = 0; i < nLinks; ++i)
    {
        // UDP sink on AP
        PacketSinkHelper sinkHelper("ns3::UdpSocketFactory",
                                     InetSocketAddress(Ipv4Address::GetAny(), port + i));
        ApplicationContainer sinkApp = sinkHelper.Install(apNodes.Get(i));
        sinkApp.Start(Seconds(0.0));
        sinkApp.Stop(Seconds(simTime));

        // Connect trace to count received bytes after warmup
        Ptr<PacketSink> sink = DynamicCast<PacketSink>(sinkApp.Get(0));

        // OnOffApplication on STA
        OnOffHelper onoff("ns3::UdpSocketFactory",
                           InetSocketAddress(apInterfaces.GetAddress(i), port + i));
        onoff.SetAttribute("DataRate", DataRateValue(DataRate(dataRate)));
        onoff.SetAttribute("PacketSize", UintegerValue(packetSize));
        onoff.SetAttribute("OnTime", StringValue("ns3::ConstantRandomVariable[Constant=1]"));
        onoff.SetAttribute("OffTime", StringValue("ns3::ConstantRandomVariable[Constant=0]"));

        ApplicationContainer onoffApp = onoff.Install(staNodes.Get(i));
        onoffApp.Start(Seconds(0.5));  // slight offset to let association complete
        onoffApp.Stop(Seconds(simTime));
    }

    // Schedule byte counting after warmup
    // We'll read PacketSink total bytes at warmup and at end
    std::vector<uint64_t> bytesAtWarmup(nLinks, 0);

    // Use a simple approach: just read total at end and subtract warmup portion
    // Actually, let's use the Rx trace callback approach
    // Reset: we'll track via PacketSink::GetTotalRx()

    Simulator::Stop(Seconds(simTime));
    Simulator::Run();

    // --- Collect results ---
    double measureTime = simTime - 0.5;  // GetTotalRx counts from t=0; subtract app start offset

    std::string fname = outDir + "/rate_mcs" + std::to_string(mcs) + "_rts" + std::to_string(rts)
                        + "_s" + std::to_string(seed) + ".csv";
    std::ofstream ofs(fname);
    ofs << "nLinks,seed,link_index,goodput_Mbps,goodput_MBps" << std::endl;

    for (uint32_t i = 0; i < nLinks; ++i)
    {
        // Get total received bytes from PacketSink
        std::string path = "/NodeList/" + std::to_string(nLinks + i)
                           + "/ApplicationList/0/$ns3::PacketSink/TotalRx";
        Ptr<PacketSink> sink = DynamicCast<PacketSink>(
            apNodes.Get(i)->GetApplication(0));
        uint64_t totalRx = sink->GetTotalRx();

        // Approximate: total bytes / measurement time
        // The warmup is handled by the saturated steady-state assumption
        double goodputMbps = (totalRx * 8.0) / (measureTime * 1e6);
        double goodputMBps = totalRx / (measureTime * 1e6);

        ofs << nLinks << "," << seed << "," << i << ","
            << std::fixed << std::setprecision(4)
            << goodputMbps << "," << goodputMBps << std::endl;
    }
    ofs.close();

    Simulator::Destroy();

    std::cout << "n=" << nLinks << " seed=" << seed
              << " -> " << fname << std::endl;

    return 0;
}
