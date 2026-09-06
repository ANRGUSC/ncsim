/*
 * Asymmetric overlapping contention domains for ncsim validation.
 *
 * Link A conflicts with B, B conflicts with A and C, and A does not
 * carrier-sense C. All links use 802.11ax, 20 MHz, 800 ns GI, no frame
 * aggregation, and saturated UDP traffic.
 */

#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/wifi-module.h"

#include <fstream>
#include <iomanip>
#include <string>

using namespace ns3;

int
main(int argc, char* argv[])
{
    uint32_t seed = 1;
    double simTime = 30.0;
    std::string outDir = "/results";
    CommandLine cmd(__FILE__);
    cmd.AddValue("seed", "RNG seed and run", seed);
    cmd.AddValue("simTime", "Simulation duration in seconds", simTime);
    cmd.AddValue("outDir", "Output directory", outDir);
    cmd.Parse(argc, argv);

    RngSeedManager::SetSeed(seed);
    RngSeedManager::SetRun(seed);
    Config::SetDefault("ns3::WifiRemoteStationManager::RtsCtsThreshold",
                       StringValue("999999"));

    NodeContainer nodes;
    nodes.Create(6);

    YansWifiChannelHelper channel;
    channel.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel");
    channel.AddPropagationLoss("ns3::LogDistancePropagationLossModel",
                               "Exponent",
                               DoubleValue(3.0),
                               "ReferenceLoss",
                               DoubleValue(46.4));
    YansWifiPhyHelper phy;
    phy.SetChannel(channel.Create());
    phy.Set("TxPowerStart", DoubleValue(20.0));
    phy.Set("TxPowerEnd", DoubleValue(20.0));
    phy.Set("CcaEdThreshold", DoubleValue(-82.0));
    phy.Set("RxNoiseFigure", DoubleValue(6.0));
    phy.Set("ChannelSettings", StringValue("{0, 20, BAND_5GHZ, 0}"));

    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211ax);
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                 "DataMode",
                                 StringValue("HeMcs5"),
                                 "ControlMode",
                                 StringValue("HeMcs0"));
    WifiMacHelper mac;
    mac.SetType("ns3::AdhocWifiMac");
    NetDeviceContainer devices = wifi.Install(phy, mac, nodes);

    for (uint32_t index = 0; index < devices.GetN(); ++index)
    {
        Ptr<WifiNetDevice> device = DynamicCast<WifiNetDevice>(devices.Get(index));
        device->GetMac()->SetAttribute("BE_MaxAmpduSize", UintegerValue(0));
        device->GetMac()->SetAttribute("BE_MaxAmsduSize", UintegerValue(0));
        device->GetHeConfiguration()->SetAttribute("GuardInterval",
                                                    TimeValue(NanoSeconds(800)));
    }

    Ptr<ListPositionAllocator> positions = CreateObject<ListPositionAllocator>();
    positions->Add(Vector(0.0, 0.0, 0.0));
    positions->Add(Vector(30.0, 0.0, 0.0));
    positions->Add(Vector(0.0, 60.0, 0.0));
    positions->Add(Vector(30.0, 60.0, 0.0));
    positions->Add(Vector(0.0, 120.0, 0.0));
    positions->Add(Vector(30.0, 120.0, 0.0));
    MobilityHelper mobility;
    mobility.SetPositionAllocator(positions);
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(nodes);

    InternetStackHelper internet;
    internet.Install(nodes);
    Ipv4AddressHelper addresses;
    addresses.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer interfaces = addresses.Assign(devices);

    const uint32_t transmitters[3] = {0, 2, 4};
    const uint32_t receivers[3] = {1, 3, 5};
    const uint16_t basePort = 9000;
    ApplicationContainer sinks;
    for (uint32_t link = 0; link < 3; ++link)
    {
        PacketSinkHelper sink(
            "ns3::UdpSocketFactory",
            InetSocketAddress(Ipv4Address::GetAny(), basePort + link));
        ApplicationContainer sinkApp = sink.Install(nodes.Get(receivers[link]));
        sinkApp.Start(Seconds(0.0));
        sinkApp.Stop(Seconds(simTime));
        sinks.Add(sinkApp);

        OnOffHelper source(
            "ns3::UdpSocketFactory",
            InetSocketAddress(interfaces.GetAddress(receivers[link]), basePort + link));
        source.SetAttribute("DataRate", DataRateValue(DataRate("200Mbps")));
        source.SetAttribute("PacketSize", UintegerValue(1472));
        source.SetAttribute(
            "OnTime", StringValue("ns3::ConstantRandomVariable[Constant=1]"));
        source.SetAttribute(
            "OffTime", StringValue("ns3::ConstantRandomVariable[Constant=0]"));
        ApplicationContainer sourceApp = source.Install(nodes.Get(transmitters[link]));
        sourceApp.Start(Seconds(0.5));
        sourceApp.Stop(Seconds(simTime));
    }

    Simulator::Stop(Seconds(simTime));
    Simulator::Run();

    const double measureTime = simTime - 0.5;
    double aggregate = 0.0;
    double rates[3] = {0.0, 0.0, 0.0};
    for (uint32_t link = 0; link < 3; ++link)
    {
        Ptr<PacketSink> sink = DynamicCast<PacketSink>(sinks.Get(link));
        rates[link] = sink->GetTotalRx() / (measureTime * 1e6);
        aggregate += rates[link];
    }

    std::string filename = outDir + "/asymmetric_seed" +
                           std::to_string(seed) + ".csv";
    std::ofstream output(filename);
    output << "seed,link,goodput_MBps,aggregate_MBps\n";
    const char* labels[3] = {"A", "B", "C"};
    for (uint32_t link = 0; link < 3; ++link)
    {
        output << seed << "," << labels[link] << "," << std::fixed
               << std::setprecision(6) << rates[link] << "," << aggregate
               << "\n";
    }
    output.close();
    Simulator::Destroy();
    return 0;
}
