import pysam
import argparse
import os
import gzip
import pprint

pp = pprint.PrettyPrinter(indent=4)


def read_regions(regionsfile,host,additives,viruses):
    host=host.split(",")
    additives=additives.split(",")
    viruses=viruses.split(",")
    infile=open(regionsfile,'r')
    regions=dict()
    for l in infile.readlines():
        l = l.strip().split("\t")
        region_name=l[0]
        regions[region_name]=dict()
        regions[region_name]['sequences']=dict()
        if region_name in host:
            regions[region_name]['host_additive_virus']="host"
        elif region_name in additives:
            regions[region_name]['host_additive_virus']="additive"
        elif region_name in viruses:
            regions[region_name]['host_additive_virus']="virus"
        else:
            exit("%s has unknown region. Its not a host or a additive or a virus!!")
        sequence_names=l[1].split()
        for s in sequence_names:
            regions[region_name]['sequences'][s]=1
    return regions        

def _get_host_additive_virus(regions,seqname):
    for k,v in regions.items():
        if seqname in v['sequences']:
            return v['host_additive_virus']
    else:
        exit("Sequence: %s does not have a region."%(seqname))

def _get_regionname_from_seqname(regions,seqname):
    for k,v in regions.items():
        if seqname in v['sequences']:
            return k
    else:
        exit("Sequence: %s does not have a region."%(seqname))


def main():
    # debug = True
    debug = False
    parser = argparse.ArgumentParser(
    )
    # INPUTs
    parser.add_argument("-i","--inbam",dest="inbam",required=True,type=str,
        help="Input BAM file")
    parser.add_argument('-r',"--rid2jid",dest="rid2jid",required=True,type=str,
        help="readID to junctionID lookup")
    parser.add_argument('-t','--sample_counts_table', dest='countstable', type=str, required=True,
        help='circExplore per-sample counts table')	# get coordinates of the circRNA
    parser.add_argument("-s",'--sample_name', dest='samplename', type=str, required=False, default = 'sample1',
        help='Sample Name: SM for RG')
    parser.add_argument('-p',"--pe",dest="pe",required=False,action='store_true', default=False,
        help="set this if BAM is paired end")
    parser.add_argument("-l",'--library', dest='library', type=str, required=False, default = 'lib1',
        help='Sample Name: LB for RG')
    parser.add_argument("-f",'--platform', dest='platform', type=str, required=False, default = 'illumina',
        help='Sample Name: PL for RG')
    parser.add_argument("-u",'--unit', dest='unit', type=str, required=False, default = 'unit1',
        help='Sample Name: PU for RG')
    parser.add_argument('--regions', dest='regions', type=str, required=True,
        help='regions file eg. ref.fa.regions')
    parser.add_argument('--host', dest='host', type=str, required=True,
        help='host name eg.hg38... single value')
    parser.add_argument('--additives', dest='additives', type=str, required=True,
        help='additive name(s) eg.ERCC... comma-separated list... all BSJs in this region are filtered out')
    parser.add_argument('--viruses', dest='viruses', type=str, required=True,
        help='virus name(s) eg.NC_009333.1... comma-separated list')
    # OUTPUTs
    parser.add_argument("-o","--outbam",dest="outbam",required=True,type=str,
        help="Output \"primary alignment near BSJ\" only BAM file")
    parser.add_argument("--splicedbam",dest="splicedbam",required=True,type=str,
        help="Output \"primary spliced alignment\" only BAM file")
    parser.add_argument("--splicedbsjbam",dest="splicedbsjbam",required=True,type=str,
        help="Output \"primary spliced alignment near BSJ\" only BAM file")
    parser.add_argument("--outputhostbams",dest="outputhostbams",required=False,action='store_true', default=False,
        help="Output individual host BAM files")
    parser.add_argument("--outputvirusbams",dest="outputvirusbams",required=False,action='store_true', default=False,
        help="Output individual virus BAM files")
    parser.add_argument("--outdir",dest="outdir",required=False,type=str,
        help="Output folder for the individual BAM files (required only if --outputhostbams or --outputvirusbams is used).")
    parser.add_argument("-c","--countsfound",dest="countsfound",required=True,type=argparse.FileType('w', encoding='UTF-8'),
        help="Output TSV file with counts of junctions found")


    args = parser.parse_args()
    print("Reading...rid2jid!...")
    rid2jid = dict()
    with gzip.open(args.rid2jid,'rt') as tfile:
        for l in tfile:
            l=l.strip().split("\t")
            rid2jid[l[0]]=l[1]
    tfile.close()
    print("Done reading...%d rid2jid's!"%(len(rid2jid)))

    samfile = pysam.AlignmentFile(args.inbam, "rb")
    samheader = samfile.header.to_dict()
    samheader['RG']=list()
    junctionsfile = open(args.countstable,'r')
    print("Reading...junctions!...")
    count=0
    junction_counts=dict()
    spliced=dict()
    splicedbsj=dict()
    splicedbsjjid=dict()
    for l in junctionsfile.readlines():
        count+=1
        if "read_count" in l: continue
        l = l.strip().split("\t")
        chrom = l[0]
        start = l[1]
        end = str(int(l[2])-1)
        jid   = chrom+"##"+start+"##"+end                     # create a unique junction ID for each line in the BSJ junction file and make it the dict key ... easy for searching!
        samheader['RG'].append({'ID':jid ,  'LB':args.library, 'PL':args.platform, 'PU':args.unit,'SM':args.samplename})
        junction_counts[jid] = dict()
        splicedbsjjid[jid] = dict()
    junctionsfile.close()
    sequences = list()
    for v in samheader['SQ']:
        sequences.append(v['SN'])
    seqname2regionname=dict()
    hosts=set()
    viruses=set()
    regions = read_regions(regionsfile=args.regions,host=args.host,additives=args.additives,viruses=args.viruses)
    for s in sequences:
        hav = _get_host_additive_virus(regions,s)
        if hav == "host":
            hostname = _get_regionname_from_seqname(regions,s)
            seqname2regionname[s]=hostname
            hosts.add(hostname)
        if hav == "virus":
            virusname = _get_regionname_from_seqname(regions,s)
            seqname2regionname[s]=virusname
            viruses.add(virusname)
    print("Done reading %d junctions."%(count))
    
    outbam = pysam.AlignmentFile(args.outbam, "wb", header=samheader)
    splicedbam = pysam.AlignmentFile(args.splicedbam, "wb", header=samheader)
    splicedbsjbam = pysam.AlignmentFile(args.splicedbsjbam, "wb", header=samheader)
    outputbams = dict()
    if args.outputhostbams:
        for h in hosts:
            outbamname = os.path.join(args.outdir,args.samplename+"."+h+".BSJ.bam")
            outputbams[h] = pysam.AlignmentFile(outbamname, "wb", header = samheader)
    if args.outputvirusbams:
        for v in viruses:
            outbamname = os.path.join(args.outdir,args.samplename+"."+v+".BSJ.bam")
            outputbams[v] = pysam.AlignmentFile(outbamname, "wb", header = samheader)            
    lenoutputbams = len(outputbams)
    # pp.pprint(rid2jid)
    print("Opened output BAMs for writing...")
    spliced=dict() # 1=spliced
    splicedbsj=dict()
    count1=0    # total reads
    count2=0    # total reads near BSJ
    count3=0    # total spliced reads
    count4=0    # total spliced reads near BSJ
    print("Reading alignments...")
    mate_already_counted1=dict()
    mate_already_counted2=dict()
    # mate_already_counted3=dict() # not needed as similar to the "spliced" dict
    # mate_already_counted4=dict() # not needed as similar to "spliced" dict have value 2
    for read in samfile.fetch():
        if args.pe and ( read.reference_id != read.next_reference_id ): continue    # only works for PE ... for SE read.next_reference_id is -1
        if args.pe and ( not read.is_proper_pair ): continue
        if read.is_secondary or read.is_supplementary or read.is_unmapped : continue
        rid=read.query_name
# count read if it has not been counted yet
        if not rid in mate_already_counted1:
            mate_already_counted1[rid]=1
            count1+=1
# find cigar tuple, cigar string and generate a cigar string order
# if 0 is followed by 3 in the "cigarstringorder" value (can happen more than once in multi-spliced reads)
# then the read is spliced
        cigar=read.cigarstring
        cigart=read.cigartuples
        cigart=cigart[list(map(lambda z:z[0],cigart)).index(0):]
        cigarstringorder=""
        for j in range(len(cigart)):
            cigarstringorder+=str(cigart[j][0])
# cigarstringorder can be like 034 or 03034 or 03 or 0303
# check if the rid is already found to be spliced ... if not then check if it is
        if not rid in spliced:
            if "03" in cigarstringorder: # aka read is spliced
                count3+=1
                spliced[rid]=1
# check if the rid exists in the rid2jid lookup table
        if rid in rid2jid:  # does this rid have a corresponding BSJ??
# if rid is in rid2jid lookuptable and it is not previously counted then count it as "linear" read for that BSJ
            if not rid in mate_already_counted2:
                mate_already_counted2[rid]=1
                count2+=1
            jid = rid2jid[rid]
            # print(rid,jid ) 
            x=jid.split("##")
            chrom=x[0]
            s=int(x[1])
            e=int(x[2])
# "junction_counts" is number of counts of linear BSJ reads found for each BSJ
            if not rid in junction_counts[jid] :
                junction_counts[jid][rid]=1
            read.set_tag("RG", jid , value_type="Z")
            outbam.write(read)
            if lenoutputbams != 0:
                regionname=_get_regionname_from_seqname(regions,chrom)
                if regionname in hosts and args.outputhostbams:
                    outputbams[regionname].write(read)
                if regionname in viruses and args.outputvirusbams:
                    outputbams[regionname].write(read)
# check if this rid's .. this alignment is spliced!
# rid could be in spliced but this may be an unspliced mate
            if rid in spliced and "03" in cigarstringorder:
                if not rid in splicedbsj:
# CIGAR has match ... followed by skip ... aka spliced read
# find number of splices
# nsplices is the number of times "03" is found in cigarstringorder
# if nsplices is gt than 1 then we have to get the coordinates of all the matches and 
# try to compare each one with the BSJ coordinates
                    nsplices = cigarstringorder.count("03")
                    if nsplices == 1:
                        start=int(read.reference_start)+int(cigart[0][1])+1
                        end=int(start)+int(cigart[1][1])-1
                        if abs(int(start)-int(s))<3 or abs(int(end)-int(e))<3: # include 2,1,0,-1,-2
                            splicedbsj[rid]=1  # aka read is spliced and is spliced at BSJ
                            count4+=1
                            splicedbsjjid[jid][rid]=1
                    else:   # read has multiple splicing events
                        for j in range(len(cigart)-1):
                            if cigart[j][0]==0 and cigart[j+1][0]==3:
                                add_coords = 0
                                for k in range(j+1):
                                    add_coords+=int(cigart[k][1])
                                start=int(read.reference_start)+add_coords+1
                                end=int(start)+int(cigart[j+1][1])-1
                                if abs(int(start)-int(s))<3 or abs(int(end)-int(e))<3: # include 2,1,0,-1,-2
                                    splicedbsj[rid]=1  # aka read is spliced and is spliced at BSJ
                                    count4+=1
                                    splicedbsjjid[jid][rid]=1
                                    break
        if (count1%10000==0):
            print("...Processed %d reads/readpairs (%d  were spliced! %d linear around BSJ! %d spliced at BSJ)"%(count1,len(spliced),count2,len(splicedbsj)))
    print("Done processing alignments: %d reads/readpairs (%d  were spliced! %d linear around BSJ! %d spliced at BSJ)"%(count1,len(spliced),count2,len(splicedbsj)))
    if lenoutputbams != 0:
        for k,v in outputbams.items():
            v.close()
    samfile.reset()
    print("Writing spliced BAMs ...")

    for read in samfile.fetch():
        rid = read.query_name
        if rid in spliced : splicedbam.write(read)
        if rid in splicedbsj : 
            jid = rid2jid[rid]
            read.set_tag("RG", jid ,  value_type="Z") 
            splicedbsjbam.write(read)

    samfile.close()
    outbam.close()
    splicedbam.close()
    splicedbsjbam.close()
    print("Closing all BAMs")
    args.countsfound.write("#chrom\tstart\tend\tfound_linear_BSJ_reads\tspliced_linear_BSJ_reads\n")
    for jid in junction_counts.keys():
        x=jid.split("##")
        chrom=x[0]
        start=int(x[1])
        end=int(x[2])+1
        linear_count=len(junction_counts[jid])
        spliced_linear_count=len(splicedbsjjid[jid])
        args.countsfound.write("%s\t%d\t%d\t%d\t%d\n"%(chrom,start,end,linear_count,spliced_linear_count))
    args.countsfound.close()
    print("DONE!!")


if __name__ == "__main__":
    main()