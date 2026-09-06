/* Controlled UDP demand transitions; no workflow or transport-level comparison. */
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/wifi-module.h"
#include "ns3/mobility-module.h"
#include "ns3/applications-module.h"
#include "ns3/traffic-control-module.h"
#include <array>
#include <cmath>
#include <fstream>
#include <iomanip>
using namespace ns3;

std::array<std::array<uint64_t, 50>, 2> bytes{};
std::array<uint64_t, 2> lateBytes{};
void Receive(uint32_t link, Ptr<const Packet> packet, const Address&)
{
    double now = Simulator::Now().GetSeconds();
    int bin = int(std::floor((now - 0.5) / 0.1));
    if (bin >= 0 && bin < 50) bytes[link][bin] += packet->GetSize();
    if (link == 1 && now >= 4.0) lateBytes[link] += packet->GetSize();
}

int main(int argc, char** argv)
{
    double separation = 40;
    uint32_t seed = 1;
    std::string outDir = "/results";
    CommandLine cmd(__FILE__);
    cmd.AddValue("separation", "Vertical spacing of two 30 m links", separation);
    cmd.AddValue("seed", "RNG seed and run", seed);
    cmd.AddValue("outDir", "Output directory", outDir);
    cmd.Parse(argc, argv);
    RngSeedManager::SetSeed(seed);
    RngSeedManager::SetRun(seed);
    // Bound queued demand after source shutdown; retries can still drain later.
    Config::SetDefault("ns3::WifiMacQueue::MaxSize", QueueSizeValue(QueueSize("1p")));
    Config::SetDefault("ns3::WifiRemoteStationManager::RtsCtsThreshold", UintegerValue(999999));
    Config::SetDefault("ns3::WifiRemoteStationManager::MaxSsrc", UintegerValue(7));
    Config::SetDefault("ns3::WifiRemoteStationManager::MaxSlrc", UintegerValue(4));
    NodeContainer nodes;
    nodes.Create(4);
    YansWifiChannelHelper channel;
    channel.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel");
    channel.AddPropagationLoss("ns3::LogDistancePropagationLossModel", "Exponent", DoubleValue(3),
                              "ReferenceLoss", DoubleValue(46.4));
    YansWifiPhyHelper phy;
    phy.SetChannel(channel.Create());
    phy.Set("TxPowerStart", DoubleValue(20));
    phy.Set("TxPowerEnd", DoubleValue(20));
    phy.Set("CcaEdThreshold", DoubleValue(-82));
    phy.Set("RxNoiseFigure", DoubleValue(6));
    phy.Set("ChannelSettings", StringValue("{0, 20, BAND_5GHZ, 0}"));
    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211ax);
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager", "DataMode", StringValue("HeMcs5"),
                                "ControlMode", StringValue("OfdmRate24Mbps"));
    WifiMacHelper mac;
    mac.SetType("ns3::AdhocWifiMac");
    auto devices = wifi.Install(phy, mac, nodes);
    for (uint32_t i = 0; i < 4; ++i) {
        auto dev = DynamicCast<WifiNetDevice>(devices.Get(i));
        for (std::string ac : {"BE", "BK", "VI", "VO"}) {
            dev->GetMac()->SetAttribute(ac + "_MaxAmpduSize", UintegerValue(0));
            dev->GetMac()->SetAttribute(ac + "_MaxAmsduSize", UintegerValue(0));
        }
        dev->GetHeConfiguration()->SetAttribute("GuardInterval", TimeValue(NanoSeconds(800)));
    }
    MobilityHelper mobility;
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    auto positions = CreateObject<ListPositionAllocator>();
    positions->Add(Vector(0, 0, 0)); positions->Add(Vector(30, 0, 0));
    positions->Add(Vector(0, separation, 0)); positions->Add(Vector(30, separation, 0));
    mobility.SetPositionAllocator(positions);
    mobility.Install(nodes);
    InternetStackHelper internet;
    internet.Install(nodes);
    Ipv4AddressHelper ipv4;
    ipv4.SetBase("10.1.1.0", "255.255.255.0");
    auto addresses = ipv4.Assign(devices);
    // Eliminate network-layer startup and qdisc backlogs from this MAC test.
    TrafficControlHelper trafficControl;
    trafficControl.Uninstall(devices);
    for (uint32_t i = 0; i < 4; ++i) {
        auto cache = CreateObject<ArpCache>();
        for (uint32_t j = 0; j < 4; ++j) if (i != j) {
            auto entry = cache->Add(addresses.GetAddress(j));
            entry->SetMacAddress(devices.Get(j)->GetAddress());
            entry->MarkPermanent();
        }
        nodes.Get(i)->GetObject<Ipv4L3Protocol>()->GetInterface(1)->SetArpCache(cache);
    }
    for (uint32_t link = 0; link < 2; ++link) {
        uint16_t port = 9000 + link;
        PacketSinkHelper sink("ns3::UdpSocketFactory", InetSocketAddress(Ipv4Address::GetAny(), port));
        auto sinks = sink.Install(nodes.Get(2 * link + 1));
        sinks.Start(Seconds(0)); sinks.Stop(Seconds(6));
        sinks.Get(0)->TraceConnectWithoutContext("Rx", MakeBoundCallback(&Receive, link));
        OnOffHelper source("ns3::UdpSocketFactory", InetSocketAddress(addresses.GetAddress(2 * link + 1), port));
        source.SetAttribute("DataRate", DataRateValue(DataRate("200Mbps")));
        source.SetAttribute("PacketSize", UintegerValue(1472));
        source.SetAttribute("OnTime", StringValue("ns3::ConstantRandomVariable[Constant=1]"));
        source.SetAttribute("OffTime", StringValue("ns3::ConstantRandomVariable[Constant=0]"));
        auto sources = source.Install(nodes.Get(2 * link));
        sources.Start(Seconds(link == 0 ? 0.5 : 2));
        sources.Stop(Seconds(link == 0 ? 5.5 : 4));
    }
    Simulator::Stop(Seconds(6));
    Simulator::Run();
    std::ofstream out(outDir + "/dynamic_s" + std::to_string(int(separation)) + "_seed" + std::to_string(seed) + ".csv");
    out << "separation,seed,link_index,start_s,end_s,payload_bytes,late_payload_bytes\n";
    for (uint32_t link = 0; link < 2; ++link)
        for (uint32_t bin = 0; bin < 50; ++bin)
            out << separation << ',' << seed << ',' << link << ',' << std::fixed << std::setprecision(1)
                << .5 + .1 * bin << ',' << .6 + .1 * bin << ',' << bytes[link][bin] << ',' << lateBytes[link] << '\n';
    Simulator::Destroy();
}
