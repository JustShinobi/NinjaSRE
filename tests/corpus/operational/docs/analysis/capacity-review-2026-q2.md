# Capacity review, second quarter

## What was measured

Allocated against used memory and storage for every guest, and the headroom on
each node if the largest node were lost.

## What it says

The cluster survives the loss of any one node on memory. It does not survive the
loss of the node carrying the largest three guests on storage, because the
remaining datastores together hold less free space than those guests occupy.

## What it does not say

Nothing here is about the present. These are the numbers as they were measured,
and the estate is what says whether they still hold.
